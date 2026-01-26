# ============================================================
# 文件说明: feeding_analysis_service_v3.py - 投料分析服务 (v3.0 简化版)
# ============================================================
# 核心改进:
# 1. 使用内存队列缓存5分钟的重量数据
# 2. 简化下料速度计算: (谷底前一个点 - 谷底) / 时间
# 3. 简化投料计算: 下料速度 × 时间 + 净增量
# 4. 缓存上次的下料速度，用于特殊情况
# ============================================================

import asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional, Deque
from collections import deque

from config import get_settings
from app.core.influxdb import get_influx_client
from app.services.history_query_service import HistoryQueryService
from app.services.polling_service import get_latest_data
from influxdb_client import Point
from influxdb_client.client.write_api import SYNCHRONOUS

settings = get_settings()


class FeedingAnalysisServiceV3:
    """投料分析服务 v3.0 - 简化版"""
    
    def __init__(self):
        self._is_running = False
        self._task = None
        
        # ============================================================
        # 核心参数
        # ============================================================
        self.run_interval_minutes = 5      # 运行频率: 5分钟
        self.queue_window_minutes = 5      # 队列窗口: 5分钟
        self.poll_interval_seconds = 6     # PLC轮询间隔: 6秒
        
        # ============================================================
        # 算法参数
        # ============================================================
        self.min_feeding_threshold = 10.0  # 最小投料阈值 (kg)
        self.rising_threshold = 5.0        # 上升阈值 (kg)
        
        # ============================================================
        # 内存队列缓存 (每个设备一个队列)
        # ============================================================
        # 结构: {device_id: deque([{"time": datetime, "value": float}, ...])}
        self.weight_queues: Dict[str, Deque[Dict]] = {}
        
        # ============================================================
        # 下料速度缓存 (用于特殊情况)
        # ============================================================
        # 结构: {device_id: float}  # kg/interval
        self.cached_feed_rates: Dict[str, float] = {}
        
        # ============================================================
        # 累积投料状态 (v3.1 新增 - 跨周期累积)
        # ============================================================
        # 用于记录正在进行中的投料，跨越多个5分钟周期
        # 结构: {device_id: {
        #   "valley_idx": int,            # 谷底在队列中的索引
        #   "valley_val": float,          # 谷底值
        #   "valley_time": datetime,      # 谷底时间
        #   "feed_rate": float,           # 下料速度
        #   "last_val": float,            # 上次的值
        #   "last_time": datetime         # 上次的时间
        # }}
        self.feeding_states: Dict[str, Dict] = {}
        
        self.history_service = HistoryQueryService()
    
    def start(self):
        """启动后台分析任务"""
        if self._is_running:
            return
        self._is_running = True
        self._task = asyncio.create_task(self._scheduled_loop())
        print(f"🚀 [FeedingServiceV3] 投料分析服务已启动 (v3.0 简化版)")
        print(f"   ⏱️  检测频率: {self.run_interval_minutes} 分钟")
        print(f"   📊 队列窗口: {self.queue_window_minutes} 分钟")
        print(f"   🎯 投料阈值: {self.min_feeding_threshold} kg")
    
    def stop(self):
        """停止服务"""
        self._is_running = False
        if self._task:
            self._task.cancel()
        print(f"🛑 [FeedingServiceV3] 投料分析服务已停止")
    
    async def _scheduled_loop(self):
        """调度循环"""
        await asyncio.sleep(30)  # 初次启动等待30秒
        
        while self._is_running:
            try:
                print(f"\n{'='*60}")
                print(f"📊 [FeedingServiceV3] 开始执行投料分析任务 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
                print(f"{'='*60}")
                
                await self._analyze_feeding_job()
                
                print(f"✅ [FeedingServiceV3] 分析任务完成，下次运行在 {self.run_interval_minutes} 分钟后")
            except Exception as e:
                print(f"❌ [FeedingServiceV3] 分析任务异常: {e}")
                import traceback
                traceback.print_exc()
            
            await asyncio.sleep(self.run_interval_minutes * 60)
    
    async def _analyze_feeding_job(self):
        """执行具体的分析逻辑"""
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(minutes=self.queue_window_minutes)
        
        # 1. 获取所有料仓设备
        hopper_devices = self._get_hopper_devices()
        print(f"   📋 目标设备: {len(hopper_devices)} 台")
        
        results = []
        total_events = 0
        
        for device_id in hopper_devices:
            await asyncio.sleep(1)  # 延迟1秒
            
            # 2. 更新设备的重量队列
            self._update_weight_queue(device_id, start_time, now)
            
            # 3. 分析队列中的投料事件
            feeding_events = self._analyze_queue(device_id)
            
            if feeding_events:
                results.extend(feeding_events)
                total_events += len(feeding_events)
                print(f"      ✅ {device_id}: 发现 {len(feeding_events)} 次投料")
        
        # 4. 批量保存结果
        if results:
            self._save_feeding_records(results)
            print(f"\n   💾 本次分析: 共发现 {total_events} 次投料事件")
        else:
            print(f"\n   ℹ️  本次分析: 未发现新的投料事件")
    
    def _get_hopper_devices(self) -> List[str]:
        """获取所有带料仓的设备ID"""
        devices = []
        latest = get_latest_data()
        
        for device_id, data in latest.items():
            if "no_hopper" in device_id:
                continue
            
            has_weigh = False
            if 'modules' in data:
                for m_data in data['modules'].values():
                    if m_data.get('module_type') == 'WeighSensor':
                        has_weigh = True
                        break
            
            if has_weigh:
                devices.append(device_id)
        
        if not devices:
            return [
                'short_hopper_1', 'short_hopper_2', 'short_hopper_3', 'short_hopper_4',
                'long_hopper_1', 'long_hopper_2', 'long_hopper_3'
            ]
        return devices
    
    def _update_weight_queue(self, device_id: str, start: datetime, end: datetime):
        """
        更新设备的重量队列
        
        Args:
            device_id: 设备ID
            start: 开始时间
            end: 结束时间
        """
        # 查询最近5分钟的重量数据
        query = f'''
        from(bucket: "{settings.influx_bucket}")
            |> range(start: {start.isoformat().replace("+00:00", "Z")}, stop: {end.isoformat().replace("+00:00", "Z")})
            |> filter(fn: (r) => r["_measurement"] == "sensor_data")
            |> filter(fn: (r) => r["device_id"] == "{device_id}")
            |> filter(fn: (r) => r["_field"] == "weight")
            |> sort(columns: ["_time"])
        '''
        
        try:
            result = self.history_service.query_api.query(query)
            data_points = []
            
            for table in result:
                for record in table.records:
                    val = record.get_value()
                    if val is not None and val > 0:
                        data_points.append({
                            "time": record.get_time(),
                            "value": float(val)
                        })
            
            # 更新队列
            if device_id not in self.weight_queues:
                self.weight_queues[device_id] = deque(maxlen=100)  # 最多保留100个点
            
            self.weight_queues[device_id].clear()
            self.weight_queues[device_id].extend(data_points)
            
            print(f"      🔍 {device_id}: 队列更新，{len(data_points)} 个数据点")
        
        except Exception as e:
            print(f"      ❌ {device_id}: 队列更新失败 - {e}")
    
    def _analyze_queue(self, device_id: str) -> List[Point]:
        """
        分析队列中的投料事件 (v3.1 累积投料版)
        
        核心改进: 累积连续的投料，直到出现峰值+下降才生成记录
        
        算法流程:
        1. 检查是否有正在进行的投料 (feeding_states)
        2. 如果有，继续累积；如果没有，检测新的投料起点
        3. 只有当检测到明显下降时，才认为投料结束，生成记录
        4. 如果一直上升，保持累积状态，等待下次分析
        
        示例场景:
        第1次分析 (5分钟): 100 → 110 → 120 → 130 (一直上升)
          → 不生成记录，保存状态 (valley=100, last=130)
        
        第2次分析 (10分钟): 130 → 140 → 150 → 145 (出现下降)
          → 生成记录: 投料量 = (150 - 100) + 补偿
        
        这样，连续10分钟的投料只生成1条记录！
        
        Args:
            device_id: 设备ID
            
        Returns:
            List[Point]: InfluxDB Point 列表
        """
        if device_id not in self.weight_queues:
            return []
        
        queue = list(self.weight_queues[device_id])
        if len(queue) < 3:
            return []
        
        events = []
        
        # ============================================================
        # 检查是否有正在进行的投料
        # ============================================================
        if device_id in self.feeding_states:
            state = self.feeding_states[device_id]
            print(f"         🔄 {device_id}: 继续累积投料 (谷底={state['valley_val']:.1f}kg)")
            
            # 从队列中找到当前的峰值
            peak_idx = len(queue) - 1
            peak_val = queue[peak_idx]['value']
            peak_time = queue[peak_idx]['time']
            
            # 检查是否出现下降 (投料结束)
            has_decline = False
            for i in range(len(queue) - 1, 0, -1):
                if queue[i]['value'] < queue[i-1]['value'] - self.rising_threshold:
                    # 找到下降点，说明投料结束
                    peak_idx = i - 1
                    peak_val = queue[peak_idx]['value']
                    peak_time = queue[peak_idx]['time']
                    has_decline = True
                    break
            
            if has_decline:
                # 投料结束，生成记录
                valley_val = state['valley_val']
                valley_time = state['valley_time']
                feed_rate = state['feed_rate']
                
                raw_increase = peak_val - valley_val
                duration_seconds = (peak_time - valley_time).total_seconds()
                intervals = int(duration_seconds / self.poll_interval_seconds)
                compensation = feed_rate * intervals
                total_added = raw_increase + compensation
                
                p = Point("feeding_records") \
                    .tag("device_id", device_id) \
                    .field("added_weight", float(total_added)) \
                    .field("raw_increase", float(raw_increase)) \
                    .field("compensation", float(compensation)) \
                    .field("feed_rate_per_interval", float(feed_rate)) \
                    .field("intervals", int(intervals)) \
                    .field("duration_seconds", int(duration_seconds)) \
                    .field("valley_weight", float(valley_val)) \
                    .field("peak_weight", float(peak_val)) \
                    .time(valley_time)
                
                events.append(p)
                
                print(f"         ✅ 累积投料完成: {valley_time.strftime('%H:%M:%S')} → {peak_time.strftime('%H:%M:%S')}, "
                      f"投料量={total_added:.1f}kg (净增={raw_increase:.1f}kg, 补偿={compensation:.1f}kg, "
                      f"持续={duration_seconds:.0f}秒)")
                
                # 清除状态
                del self.feeding_states[device_id]
            else:
                # 投料未结束，更新状态
                self.feeding_states[device_id]['last_val'] = peak_val
                self.feeding_states[device_id]['last_time'] = peak_time
                print(f"         ⏳ {device_id}: 投料持续中 (当前={peak_val:.1f}kg)")
        
        else:
            # ============================================================
            # 没有正在进行的投料，检测新的投料起点
            # ============================================================
            i = 1
            while i < len(queue):
                curr = queue[i]
                prev = queue[i - 1]
                
                # 检测上升起点 (谷底)
                if curr['value'] > prev['value'] + self.rising_threshold:
                    valley_idx = i - 1
                    valley_val = prev['value']
                    valley_time = prev['time']
                    
                    # 追踪上升到峰值
                    peak_idx = i
                    while peak_idx < len(queue) - 1:
                        if queue[peak_idx + 1]['value'] > queue[peak_idx]['value']:
                            peak_idx += 1
                        else:
                            # 检查是否真的下降
                            if queue[peak_idx]['value'] - queue[peak_idx + 1]['value'] > self.rising_threshold:
                                break
                            peak_idx += 1
                    
                    # 边缘保护: 如果到了队列末尾还在上升，说明投料未结束
                    if peak_idx >= len(queue) - 1:
                        # 保存状态，等待下次分析
                        feed_rate = self._calculate_feed_rate_per_interval(queue, valley_idx, device_id)
                        
                        self.feeding_states[device_id] = {
                            'valley_idx': valley_idx,
                            'valley_val': valley_val,
                            'valley_time': valley_time,
                            'feed_rate': feed_rate,
                            'last_val': queue[peak_idx]['value'],
                            'last_time': queue[peak_idx]['time']
                        }
                        
                        print(f"         🔄 {device_id}: 检测到投料开始 (谷底={valley_val:.1f}kg)，等待峰值")
                        break
                    
                    peak_val = queue[peak_idx]['value']
                    peak_time = queue[peak_idx]['time']
                    raw_increase = peak_val - valley_val
                    
                    # 阈值判断
                    if raw_increase > self.min_feeding_threshold:
                        # 投料完成，生成记录
                        feed_rate_per_interval = self._calculate_feed_rate_per_interval(queue, valley_idx, device_id)
                        intervals = peak_idx - valley_idx
                        compensation = feed_rate_per_interval * intervals
                        total_added = raw_increase + compensation
                        
                        # 缓存下料速度
                        self.cached_feed_rates[device_id] = feed_rate_per_interval
                        
                        duration_seconds = (peak_time - valley_time).total_seconds()
                        
                        p = Point("feeding_records") \
                            .tag("device_id", device_id) \
                            .field("added_weight", float(total_added)) \
                            .field("raw_increase", float(raw_increase)) \
                            .field("compensation", float(compensation)) \
                            .field("feed_rate_per_interval", float(feed_rate_per_interval)) \
                            .field("intervals", int(intervals)) \
                            .field("duration_seconds", int(duration_seconds)) \
                            .field("valley_weight", float(valley_val)) \
                            .field("peak_weight", float(peak_val)) \
                            .time(valley_time)
                        
                        events.append(p)
                        
                        print(f"         ✅ 投料事件: {valley_time.strftime('%H:%M:%S')} → {peak_time.strftime('%H:%M:%S')}, "
                              f"投料量={total_added:.1f}kg (净增={raw_increase:.1f}kg, 补偿={compensation:.1f}kg)")
                        
                        # 跳过已处理的区间
                        i = peak_idx + 1
                    else:
                        i += 1
                else:
                    i += 1
        
        return events
    
    def _calculate_feed_rate_per_interval(self, queue: List[Dict], valley_idx: int, device_id: str) -> float:
        """
        计算下料速度 (kg/interval) - 用户定制版
        
        公式: 谷底前一个点 - 谷底
        
        注意: 不除以时间，直接用间隔数乘
        
        特殊情况:
        - 如果谷底前一个点 <= 谷底 (没有下降): 使用缓存的下料速度
        - 如果没有缓存: 返回默认值 0.5 kg/interval
        
        Args:
            queue: 数据队列
            valley_idx: 谷底索引
            device_id: 设备ID
            
        Returns:
            float: 下料速度 (kg/interval)
            
        示例:
            queue = [5, 4, 2, 3, 12, 56]
            valley_idx = 2 (值=2)
            谷底前一个点 = 4
            下料速度 = 4 - 2 = 2 kg/interval
        """
        if valley_idx < 1:
            # 没有前一个点，使用缓存
            return self.cached_feed_rates.get(device_id, 0.5)
        
        valley_val = queue[valley_idx]['value']
        prev_val = queue[valley_idx - 1]['value']
        
        # 计算下降量 (kg/interval)
        drop = prev_val - valley_val
        
        if drop > 0:
            # 正常下降，返回下料速度
            return drop
        
        # 没有下降，使用缓存
        return self.cached_feed_rates.get(device_id, 0.5)
    
    def _save_feeding_records(self, points: List[Point]):
        """保存投料记录到 InfluxDB"""
        try:
            write_api = self.history_service.client.write_api(write_options=SYNCHRONOUS)
            write_api.write(bucket=settings.influx_bucket, record=points)
            print(f"   💾 已保存 {len(points)} 条投料记录到 InfluxDB")
        except Exception as e:
            print(f"   ❌ 保存投料记录失败: {e}")
            import traceback
            traceback.print_exc()


# ============================================================
# 单例导出
# ============================================================
feeding_service_v3 = FeedingAnalysisServiceV3()


# ============================================================
# 手动触发分析 (用于测试)
# ============================================================
async def manual_analyze_feeding_v3(device_ids: Optional[List[str]] = None):
    """
    手动触发投料分析 (v3.0)
    
    Args:
        device_ids: 指定设备ID列表，None表示分析所有设备
        
    Returns:
        Dict: 分析结果统计
    """
    service = FeedingAnalysisServiceV3()
    
    now = datetime.now(timezone.utc)
    start_time = now - timedelta(minutes=service.queue_window_minutes)
    
    if device_ids is None:
        device_ids = service._get_hopper_devices()
    
    results = []
    stats = {
        "total_devices": len(device_ids),
        "devices_with_events": 0,
        "total_events": 0,
        "details": []
    }
    
    for device_id in device_ids:
        service._update_weight_queue(device_id, start_time, now)
        feeding_events = service._analyze_queue(device_id)
        
        if feeding_events:
            results.extend(feeding_events)
            stats["devices_with_events"] += 1
            stats["total_events"] += len(feeding_events)
            stats["details"].append({
                "device_id": device_id,
                "events_count": len(feeding_events)
            })
    
    if results:
        service._save_feeding_records(results)
    
    return stats

