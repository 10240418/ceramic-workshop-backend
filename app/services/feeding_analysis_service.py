# ============================================================
# 文件说明: feeding_analysis_service.py - 投料自动分析服务 (v2.2 固定下料速度版)
# ============================================================
# 功能:
# 1. 自动分析: 每5分钟运行一次 (实时性提升)
# 2. 数据源: 查询InfluxDB过去30分钟的料仓重量数据 (原始6秒数据)
# 3. 算法: Valley-Peak-Compensation 算法 (识别投料事件并计算投料量)
# 4. 存储: 将计算结果存回 InfluxDB (measurement="feeding_records")
# 5. 去重: 基于 (device_id, valley_timestamp) 的内存去重机制
# ============================================================
# v2.2 核心改进 (2026-01-27):
# - 固定下料速度: 窑7654=10kg/h, 窑839=22kg/h (不再动态计算)
# - 补偿计算: 固定下料速度 × 投料持续时间 (秒)
# - 去重机制: 内存缓存已处理事件，防止5分钟检测导致重复存储
# - 边缘保护: 未完成的投料不存数据库，等待下次分析
# ============================================================
# 优化点:
# - 检测频率: 2小时 → 5分钟 (提升24倍)
# - 聚合粒度: 30分钟 → 原始数据 (6秒轮询)
# - 查询窗口: 24小时 → 30分钟 (减少查询负载)
# - 边缘保护: 增强未完成投料的检测逻辑
# ============================================================

import asyncio
import math
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional

from config import get_settings
from app.core.influxdb import get_influx_client, write_points_batch
from app.services.history_query_service import HistoryQueryService
from app.services.polling_service import get_latest_data
# 引入 InfluxDB 写入 Point 结构
from influxdb_client import Point
from influxdb_client.client.write_api import SYNCHRONOUS

settings = get_settings()

class FeedingAnalysisService:
    def __init__(self):
        self._is_running = False
        self._task = None
        
        # ============================================================
        # 🔧 核心参数优化
        # ============================================================
        self.run_interval_minutes = 5      # 运行频率: 5分钟检测一次 (原2小时)
        self.query_window_minutes = 30     # 查询窗口: 回溯30分钟 (原24小时)
        self.use_raw_data = True           # 使用原始数据 (不聚合)
        
        # ============================================================
        # 算法参数
        # ============================================================
        self.min_feeding_threshold = 10.0  # 最小投料阈值 (kg)
        self.rising_step_threshold = 5.0   # 上升步长阈值 (kg)
        self.drop_threshold = 5.0          # 下降阈值 (kg)
        self.lookahead_steps = 3           # 前瞻步数 (防止波动误判)
        
        # ============================================================
        # 固定下料速度配置 (v2.2 - 用户定制)
        # ============================================================
        # 窑7654 (short_hopper): 10 kg/h
        # 窑839 (long_hopper): 22 kg/h
        self.feed_rate_short_hopper = 10.0 / 3600.0  # kg/秒
        self.feed_rate_long_hopper = 22.0 / 3600.0   # kg/秒
        
        # ============================================================
        # 去重机制 (v2.2 - 防止重复存储)
        # ============================================================
        # 记录已处理的投料事件 (device_id, valley_time)
        # 结构: {(device_id, valley_timestamp): True}
        self.processed_events = {}
        self.max_cache_size = 1000  # 最多缓存1000条记录
        
        # ============================================================
        # 优化参数 (v2.1)
        # ============================================================
        self.boundary_extension = 15       # 边界扩展时间 (分钟)
        
        self.history_service = HistoryQueryService()

    def start(self):
        """启动后台分析任务"""
        if self._is_running:
            return
        self._is_running = True
        self._task = asyncio.create_task(self._scheduled_loop())
        print(f"🚀 [FeedingService] 投料分析服务已启动 (v2.2 固定下料速度版)")
        print(f"   ⏱️  检测频率: {self.run_interval_minutes} 分钟")
        print(f"   📊 查询窗口: {self.query_window_minutes} 分钟")
        print(f"   🎯 数据模式: {'原始数据(6秒)' if self.use_raw_data else '聚合数据'}")
        print(f"   📏 投料阈值: {self.min_feeding_threshold} kg")
        print(f"   🔧 下料速度: 窑7654={self.feed_rate_short_hopper*3600:.1f}kg/h, 窑839={self.feed_rate_long_hopper*3600:.1f}kg/h")

    def stop(self):
        """停止服务"""
        self._is_running = False
        if self._task:
            self._task.cancel()
        print(f"🛑 [FeedingService] 投料分析服务已停止")

    async def _scheduled_loop(self):
        """调度循环"""
        # 初次启动等待30秒，避免和系统初始化冲突
        await asyncio.sleep(30)
        
        while self._is_running:
            try:
                print(f"\n{'='*60}")
                print(f"📊 [FeedingService] 开始执行投料分析任务 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
                print(f"{'='*60}")
                
                await self._analyze_feeding_job()
                
                print(f"✅ [FeedingService] 分析任务完成，下次运行在 {self.run_interval_minutes} 分钟后")
            except Exception as e:
                print(f"❌ [FeedingService] 分析任务异常: {e}")
                import traceback
                traceback.print_exc()
            
            # 等待设定的间隔
            await asyncio.sleep(self.run_interval_minutes * 60)

    async def _analyze_feeding_job(self):
        """执行具体的分析逻辑 (优化版 v2.1)"""
        now = datetime.now(timezone.utc)
        
        # 优化: 边界扩展，避免漏检跨边界的投料事件
        extended_window = self.query_window_minutes + self.boundary_extension
        start_time = now - timedelta(minutes=extended_window)
        
        # 1. 获取所有料仓设备 (过滤 no_hopper)
        hopper_devices = self._get_hopper_devices()
        print(f"   📋 目标设备: {len(hopper_devices)} 台")
        print(f"   🕐 时间范围: {start_time.strftime('%H:%M:%S')} → {now.strftime('%H:%M:%S')}")
        
        results = []
        total_events = 0
        
        for device_id in hopper_devices:
            # 延迟1秒，防止高并发查询
            await asyncio.sleep(1)
            
            # 2. 查询历史数据
            records = self._query_history_weights(device_id, start_time, now)
            if not records:
                print(f"      ⚠️  {device_id}: 无数据")
                continue
            
            print(f"      🔍 {device_id}: 查询到 {len(records)} 个数据点")
                
            # 3. 计算投料量
            feeding_events = self._detect_and_calculate_feeding(records, device_id)
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
        # 从 polling_service 的 latest_data 获取设备列表最准确
        # 这里简化逻辑: 我们知道是 short_hopper_XX 和 long_hopper_XX
        # 也可以从配置读取，或者硬编码已知ID规则
        # 动态获取更好：
        devices = []
        latest = get_latest_data()
        for device_id, data in latest.items():
            if "no_hopper" in device_id:
                continue
            # 必须包含 weigh 模块
            has_weigh = False
            if 'modules' in data:
                for m_data in data['modules'].values():
                    if m_data.get('module_type') == 'WeighSensor':
                        has_weigh = True
                        break
            
            if has_weigh:
                devices.append(device_id)
        
        # 如果还在启动中没数据，使用预设列表
        if not devices:
            return [
                'short_hopper_1', 'short_hopper_2', 'short_hopper_3', 'short_hopper_4',
                'long_hopper_1', 'long_hopper_2', 'long_hopper_3'
            ]
        return devices

    def _query_history_weights(self, device_id: str, start: datetime, end: datetime) -> List[Dict]:
        """
        查询重量历史数据
        
        Args:
            device_id: 设备ID
            start: 开始时间
            end: 结束时间
            
        Returns:
            List[Dict]: 数据点列表 [{"time": datetime, "value": float}, ...]
        """
        # 根据配置决定是否聚合
        if self.use_raw_data:
            # 使用原始数据 (6秒轮询间隔)
            query = f'''
            from(bucket: "{settings.influx_bucket}")
                |> range(start: {start.isoformat().replace("+00:00", "Z")}, stop: {end.isoformat().replace("+00:00", "Z")})
                |> filter(fn: (r) => r["_measurement"] == "sensor_data")
                |> filter(fn: (r) => r["device_id"] == "{device_id}")
                |> filter(fn: (r) => r["_field"] == "weight")
                |> sort(columns: ["_time"])
            '''
        else:
            # 使用聚合数据 (向后兼容)
            query = f'''
            from(bucket: "{settings.influx_bucket}")
                |> range(start: {start.isoformat().replace("+00:00", "Z")}, stop: {end.isoformat().replace("+00:00", "Z")})
                |> filter(fn: (r) => r["_measurement"] == "sensor_data")
                |> filter(fn: (r) => r["device_id"] == "{device_id}")
                |> filter(fn: (r) => r["_field"] == "weight")
                |> aggregateWindow(every: 1m, fn: mean, createEmpty: false)
                |> yield(name: "mean")
            '''
        
        try:
            result = self.history_service.query_api.query(query)
            data_points = []
            for table in result:
                for record in table.records:
                    val = record.get_value()
                    if val is not None and val > 0:  # 过滤无效数据
                        data_points.append({
                            "time": record.get_time(),
                            "value": float(val)
                        })
            
            # 按时间排序
            data_points.sort(key=lambda x: x['time'])
            return data_points
        except Exception as e:
            print(f"      ❌ 查询 {device_id} 失败: {e}")
            return []

    def _detect_and_calculate_feeding(self, records: List[Dict], device_id: str) -> List[Point]:
        """
        核心算法: Valley-Peak-Compensation 投料检测算法 (v2.2 固定下料速度版)
        
        算法原理:
        ┌─────────────────────────────────────────────────────────┐
        │  投料过程示意图:                                          │
        │                                                          │
        │  Weight                                                  │
        │    ▲                                                     │
        │    │         Peak (投料结束)                             │
        │    │          ●                                          │
        │    │         ╱ ╲                                         │
        │    │        ╱   ╲                                        │
        │    │       ╱     ╲ (消耗下降)                            │
        │    │      ╱       ╲                                      │
        │    │     ╱ (投料)  ╲                                     │
        │    │    ╱           ╲                                    │
        │    │   ●             ●                                   │
        │    │  Valley      Next Valley                            │
        │    │  (投料开始)                                          │
        │    └──────────────────────────────────► Time            │
        │                                                          │
        │  计算公式 (v2.2 固定下料速度):                             │
        │  Total_Added = (Peak - Valley) + Compensation           │
        │                                                          │
        │  其中:                                                    │
        │  - Valley: 投料前的最低点                                 │
        │  - Peak: 投料后的最高点                                   │
        │  - Compensation: 投料过程中的消耗补偿                      │
        │    = 固定下料速度 (kg/秒) × 投料持续时间 (秒)              │
        │    窑7654: 10 kg/h                                       │
        │    窑839:  22 kg/h                                       │
        └─────────────────────────────────────────────────────────┘
        
        逻辑流程:
        1. 遍历数据点，寻找上升起点 (Valley)
        2. 追踪连续上升区间 (Rising Edge)
        3. 识别峰值点 (Peak)，带前瞻机制防止波动误判
        4. 计算消耗补偿 (使用固定下料速度)
        5. 计算总投料量 = 净增量 + 消耗补偿
        6. 边缘保护: 跳过数据末尾未完成的投料事件 (不存数据库)
        7. 去重机制: 检查是否已处理过该投料事件
        
        Args:
            records: 重量数据点列表 [{"time": datetime, "value": float}, ...]
            device_id: 设备ID
            
        Returns:
            List[Point]: InfluxDB Point 列表
        """
        events = []
        n = len(records)
        if n < 3:  # 至少需要3个点 (PreValley, Valley, Peak)
            return []

        # 冷却期: 记录上一次检测到的 Peak 索引，避免重复检测
        last_peak_idx = -1
        
        i = 1
        while i < n:
            # 跳过冷却期内的点
            if i <= last_peak_idx:
                i += 1
                continue
                
            curr = records[i]
            prev = records[i-1]
            
            # ============================================================
            # 步骤1: 检测上升起点 (Valley)
            # ============================================================
            if curr['value'] > prev['value'] + self.rising_step_threshold:
                valley_idx = i - 1
                valley_val = prev['value']
                valley_time = prev['time']
                
                # ============================================================
                # 步骤2: 追踪连续上升区间 (Rising Edge)
                # ============================================================
                peak_idx = i
                while peak_idx < n - 1:
                    next_val = records[peak_idx + 1]['value']
                    curr_val = records[peak_idx]['value']
                    
                    # 仍在上升
                    if next_val >= curr_val:
                        peak_idx += 1
                        continue
                    
                    # 检测到下降，启动前瞻机制防止波动误判
                    if next_val < curr_val:
                        # 前瞻机制: 检查未来N个点是否有反弹
                        is_fluctuation = False
                        for k in range(1, self.lookahead_steps + 1):
                            if peak_idx + 1 + k >= n:
                                break
                            future_val = records[peak_idx + 1 + k]['value']
                            if future_val >= curr_val:
                                # 发现反弹，说明是波动
                                is_fluctuation = True
                                peak_idx += k
                                break
                        
                        if is_fluctuation:
                            peak_idx += 1
                            continue
                        
                        # 确认下降: 只有显著下降才认为投料结束
                        drop_diff = curr_val - next_val
                        if drop_diff > self.drop_threshold:
                            break
                    
                    peak_idx += 1
                
                # ============================================================
                # 步骤3: 边缘保护 (防止未完成的投料事件)
                # ============================================================
                if peak_idx >= n - 1:
                    # 投料可能未结束，等待更多数据 (不存数据库)
                    print(f"         ⏳ {device_id}: 投料未完成 (边缘数据)，等待下次分析")
                    break
                
                peak_val = records[peak_idx]['value']
                peak_time = records[peak_idx]['time']
                raw_increase = peak_val - valley_val
                
                # ============================================================
                # 步骤4: 阈值判断
                # ============================================================
                if raw_increase > self.min_feeding_threshold:
                    # ============================================================
                    # 步骤5: 去重检查 (v2.2 - 防止重复存储)
                    # ============================================================
                    event_key = (device_id, int(valley_time.timestamp()))
                    if event_key in self.processed_events:
                        print(f"         ⏭️  {device_id}: 投料事件已处理 (谷底={valley_time.strftime('%H:%M:%S')})，跳过")
                        i = peak_idx + 1
                        continue
                    
                    # 计算投料持续时间 (秒)
                    duration_seconds = (peak_time - valley_time).total_seconds()
                    
                    # ============================================================
                    # 步骤6: 计算消耗补偿 (v2.2 - 固定下料速度)
                    # ============================================================
                    feed_rate = self._get_feed_rate(device_id)  # kg/秒
                    compensation = feed_rate * duration_seconds
                    total_added = raw_increase + compensation
                    
                    # ============================================================
                    # 步骤7: 构建 InfluxDB Point
                    # ============================================================
                    p = Point("feeding_records") \
                        .tag("device_id", device_id) \
                        .field("added_weight", float(total_added)) \
                        .field("raw_increase", float(raw_increase)) \
                        .field("compensation", float(compensation)) \
                        .field("feed_rate_kg_per_hour", float(feed_rate * 3600)) \
                        .field("duration_seconds", int(duration_seconds)) \
                        .field("valley_weight", float(valley_val)) \
                        .field("peak_weight", float(peak_val)) \
                        .time(valley_time)  # 使用 Valley 时间戳实现去重
                    
                    events.append(p)
                    
                    # 标记为已处理
                    self.processed_events[event_key] = True
                    
                    # 清理缓存 (防止内存溢出)
                    if len(self.processed_events) > self.max_cache_size:
                        # 删除最旧的一半
                        keys_to_remove = list(self.processed_events.keys())[:self.max_cache_size // 2]
                        for key in keys_to_remove:
                            del self.processed_events[key]
                    
                    # 设置冷却期
                    last_peak_idx = peak_idx
                    i = peak_idx + 1
                    
                    print(f"         ✅ 投料事件: {valley_time.strftime('%H:%M:%S')} → {peak_time.strftime('%H:%M:%S')}, "
                          f"投料量={total_added:.1f}kg (净增={raw_increase:.1f}kg, 补偿={compensation:.1f}kg, 下料速度={feed_rate*3600:.1f}kg/h)")
                else:
                    # 未超过阈值，继续
                    i += 1
            else:
                i += 1
                
        return events

    def _get_feed_rate(self, device_id: str) -> float:
        """
        获取设备的固定下料速度 (v2.2)
        
        根据设备类型返回固定的下料速度:
        - 窑7654 (short_hopper_1/2/3/4): 10 kg/h
        - 窑839 (long_hopper_1/2/3): 22 kg/h
        
        Args:
            device_id: 设备ID
            
        Returns:
            float: 下料速度 (kg/秒)
        """
        if device_id.startswith("short_hopper"):
            return self.feed_rate_short_hopper  # 10 kg/h
        elif device_id.startswith("long_hopper"):
            return self.feed_rate_long_hopper   # 22 kg/h
        else:
            # 默认值 (不应该到这里)
            return self.feed_rate_short_hopper

    def _calculate_consumption_rate(self, records: List[Dict], valley_idx: int, lookback: int = 5) -> float:
        """
        计算投料前的平均消耗速率 (已废弃 - v2.2 使用固定下料速度)
        
        保留此方法仅为向后兼容，实际不再使用
        """
        return 0.0  # 不再使用动态计算

    def _filter_outliers(self, records: List[Dict], threshold: float = 3.0) -> List[Dict]:
        """
        过滤异常值 (已废弃 - v2.2 不再使用)
        
        保留此方法仅为向后兼容
        """
        return records  # 不再使用异常值过滤

    def _save_feeding_records(self, points: List[Point]):
        """
        保存投料记录到 InfluxDB
        
        注意: InfluxDB 基于 (measurement, tags, timestamp) 的组合实现天然去重
        相同时间戳的记录会被自动覆盖，无需手动去重
        """
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
feeding_service = FeedingAnalysisService()


# ============================================================
# 手动触发分析 (用于测试)
# ============================================================
async def manual_analyze_feeding(device_ids: Optional[List[str]] = None):
    """
    手动触发投料分析 (用于测试或前端手动刷新)
    
    Args:
        device_ids: 指定设备ID列表，None表示分析所有设备
        
    Returns:
        Dict: 分析结果统计
    """
    service = FeedingAnalysisService()
    
    now = datetime.now(timezone.utc)
    start_time = now - timedelta(minutes=service.query_window_minutes)
    
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
        records = service._query_history_weights(device_id, start_time, now)
        if not records:
            continue
        
        feeding_events = service._detect_and_calculate_feeding(records, device_id)
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
