# ============================================================
# 文件说明: feeding_analysis_service.py - 投料自动分析服务
# ============================================================
# 功能:
# 1. 自动分析: 每6小时运行一次
# 2. 数据源: 查询InlfuxDB过去6小时的料仓重量数据 (10分钟聚合)
# 3. 算法: 识别投料事件 (重量激增) 并计算投料量
# 4. 存储: 将计算结果存回 InfluxDB (measurement="feeding_records")
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
        self.run_interval_minutes = 120   # 运行频率: 2小时检测一次
        self.query_window_hours = 24      # 查询窗口: 回溯过去24小时 (1天)
        self.aggregation_window = "30m"   # 聚合粒度: 放宽到30分钟
        self.history_service = HistoryQueryService()

    def start(self):
        """启动后台分析任务"""
        if self._is_running:
            return
        self._is_running = True
        self._task = asyncio.create_task(self._scheduled_loop())
        print(f"🚀 [FeedingService] 投料分析服务已启动 (Frequency: {self.run_interval_minutes}m, Window: {self.query_window_hours}h)")

    def stop(self):
        """停止服务"""
        self._is_running = False
        if self._task:
            self._task.cancel()

    async def _scheduled_loop(self):
        """调度循环"""
        # 初次启动等待一小段时间，避免和系统初始化冲突
        await asyncio.sleep(60)
        
        while self._is_running:
            try:
                print(f"📊 [FeedingService] 开始执行投料分析任务...")
                await self._analyze_feeding_job()
                print(f"✅ [FeedingService] 分析任务完成，下次运行在 {self.run_interval_minutes} 分钟后")
            except Exception as e:
                print(f"❌ [FeedingService] 分析任务异常: {e}")
            
            # 等待设定的间隔
            await asyncio.sleep(self.run_interval_minutes * 60)

    async def _analyze_feeding_job(self):
        """执行具体的分析逻辑"""
        now = datetime.now(timezone.utc)
        # 关键修改: 无论运行频率如何，始终回溯查询 query_window_hours 的数据
        # 这样可以确保捕获跨越边界的事件，并通过 InfluxDB 的幂等写入特性更新/修正记录
        start_time = now - timedelta(hours=self.query_window_hours)
        
        # 1. 获取所有料仓设备 (过滤 no_hopper)
        hopper_devices = self._get_hopper_devices()
        print(f"   📋 目标设备: {len(hopper_devices)} 台 ({', '.join(hopper_devices)})")
        
        results = []
        
        for device_id in hopper_devices:
            # 延迟5秒，防止高并发查询导致系统崩溃
            await asyncio.sleep(5)
            
            # 2. 查询历史数据 (聚合)
            records = self._query_history_weights(device_id, start_time, now)
            if not records:
                continue
                
            # 3. 计算投料量
            feeding_events = self._detect_and_calculate_feeding(records, device_id)
            if feeding_events:
                results.extend(feeding_events)
                print(f"      🔹 设备 {device_id}: 发现 {len(feeding_events)} 次投料")

        # 4. 批量保存结果
        if results:
            self._save_feeding_records(results)

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
        """查询聚合后的重量历史"""
        query = f'''
        from(bucket: "{settings.influx_bucket}")
            |> range(start: {start.isoformat().replace("+00:00", "Z")}, stop: {end.isoformat().replace("+00:00", "Z")})
            |> filter(fn: (r) => r["_measurement"] == "sensor_data")
            |> filter(fn: (r) => r["device_id"] == "{device_id}")
            |> filter(fn: (r) => r["_field"] == "weight")
            |> aggregateWindow(every: {self.aggregation_window}, fn: mean, createEmpty: false)
            |> yield(name: "mean")
        '''
        
        try:
            result = self.history_service.query_api.query(query)
            data_points = []
            for table in result:
                for record in table.records:
                    val = record.get_value()
                    if val is not None:
                        data_points.append({
                            "time": record.get_time(),
                            "value": float(val)
                        })
            # 按时间排序
            data_points.sort(key=lambda x: x['time'])
            return data_points
        except Exception as e:
            print(f"⚠️ 查询 {device_id} 失败: {e}")
            return []

    def _detect_and_calculate_feeding(self, records: List[Dict], device_id: str) -> List[Point]:
        """
        核心算法: 识别投料并计算 (Enhanced Logic v2 - 带去重)
        
        逻辑流程:
        1. 寻找 Valley (投料开始前的最低点)
        2. 追踪 Rising Edge (连续上升区间), 计数间隔 x
        3. 确定 Peak (投料结束后的最高点)
        4. 计算消耗补偿 Consumption
           - 寻找 Pre-Valley Slope (投料前的消耗速率)
           - Consumption = (Consumption_Rate_Per_Interval) * x
        5. Total Added = (Peak - Valley) + Consumption
        6. 阈值: Rising amount > 10kg
        7. [NEW] 去重: 每次检测后设置冷却期，防止同一上升区间被重复记录
        """
        events = []
        n = len(records)
        if n < 2:
            return []

        # 阈值: 只有上升总高度超过此值才触发复杂计算
        # 用户需求: > 10kg 即为有效投料
        THRESHOLD = 10.0 
        
        # [NEW] 冷却期: 记录上一次检测到的 Peak 索引，避免重复检测
        last_peak_idx = -1
        
        i = 1
        while i < n:
            # [NEW] 跳过冷却期内的点
            if i <= last_peak_idx:
                i += 1
                continue
                
            curr = records[i]
            prev = records[i-1]
            
            # 检测到起步上升
            if curr['value'] > prev['value'] + 5.0: # 至少有微小上升才开始追踪
                valley_idx = i - 1
                valley_val = prev['value']
                
                # 追踪连续上升 (允许偶尔持平或极小回落/抖动视为上升过程)
                # 寻找 Peak
                peak_idx = i
                while peak_idx < n - 1:
                    next_val = records[peak_idx+1]['value']
                    curr_val = records[peak_idx]['value']
                    
                    # 如果仍在上升
                    if next_val >= curr_val:
                        peak_idx += 1
                        continue
                        
                    # 如果下降了，但可能只是波动（比如下降很少），可以向后多看几个点？
                    # [FIX] 增加 Lookahead 机制，防止因临时微小波动导致投料误判提前结束
                    if next_val < curr_val:
                        # 检查未来 3 个点，看是否有反弹（超过当前值）
                        is_fluctuation = False
                        lookahead_steps = 3
                        for k in range(1, lookahead_steps + 1):
                            if peak_idx + 1 + k >= n: 
                                break # 数据不够了
                            future_val = records[peak_idx + 1 + k]['value']
                            if future_val >= curr_val:
                                # 发现后面又涨上去了，说明刚才只是波动
                                is_fluctuation = True
                                # 跳过中间的波动点，直接把 peak_idx 移到这个更高的点前一个（因为循环末尾会+1）
                                peak_idx += k 
                                break
                        
                        if is_fluctuation:
                            peak_idx += 1
                            continue # 继续追踪上升
                            
                        # 确实下降了，且短期没反弹
                        # 只有下降幅度超过阈值（例如 5.0kg）才认为是真正的结束，或者是持续下降
                        drop_diff = curr_val - next_val
                        if drop_diff > 5.0: 
                             break # 显著下降，认定投料停止
                        
                        # 如果是微小下降且没反弹（可能是平缓期），继续往后看？
                        # 这种情况下通常也认为是顶峰了，除非下降真的很小 (<5.0kg)
                        # 如果下降很小，让他继续走，可能会遇到更大的下降或上升
                        # 但为了安全，如果 continuous decrease...
                        
                    peak_idx += 1
                
                # [CRITICAL FIX] 边缘检测保护
                # 如果循环是因为到了数据末尾 (peak_idx == n-1) 而结束，说明投料过程可能仍在继续（或者刚达到峰值但还没开始下降）
                # 此时不能仓促下结论，应该跳过本次计算，等待更多数据进来后再确认
                if peak_idx >= n - 1:
                    # 记录调试信息但不保存
                    # print(f"      ⏳ 投料未结束 (Edge case): {records[valley_idx]['time']} -> {records[peak_idx]['time']}, 等待更多数据...")
                    break
                
                peak_val = records[peak_idx]['value']
                raw_increase = peak_val - valley_val
                
                # 判断是否满足 > 50kg 的触发条件
                if raw_increase > THRESHOLD:
                    # 计算持续间隔数 x
                    # 10分钟一个点。间隔数即 peak_idx - valley_idx
                    x_intervals = peak_idx - valley_idx
                    
                    # 计算 Pre-Valley 的消耗速率
                    # 寻找 valley 前面几个点来估算斜率
                    consumption_rate = 0.0
                    if valley_idx >= 1:
                        # 只看前一个区间 (PreValley - Valley)
                        # 用户: "(PreValley - Valley)"
                        pre_valley_val = records[valley_idx-1]['value']
                        rate = pre_valley_val - valley_val
                        if rate > 0:
                            consumption_rate = rate
                        
                        # 也可以多看几个取平均，但用户似乎倾向于只看前一个
                    
                    # 如果前一个没有数据（比如刚开始查），设定一个默认最小消耗速率？
                    # 暂时保持 0
                    
                    # 核心公式: Peak - Valley + (Consumption_Rate * x)
                    # 用户原话: "乘以x了"
                    compensation = consumption_rate * x_intervals
                    
                    total_added = raw_increase + compensation
                    
                    # 构建记录 
                    # [Changed] 使用 Valley (开始上升点) 作为记录时间戳，而非 Peak
                    # 这样可以保证每次计算的时间戳一致性（基于原始数据点），实现 InfluxDB 天然去重
                    p = Point("feeding_records") \
                        .tag("device_id", device_id) \
                        .field("added_weight", float(total_added)) \
                        .field("raw_increase", float(raw_increase)) \
                        .field("duration_intervals", int(x_intervals)) \
                        .field("compensation", float(compensation)) \
                        .time(records[valley_idx]['time'])
                    
                    events.append(p)
                    
                    # [CRITICAL] 设置冷却期: 跳过已处理的整个上升区间
                    # 下一次检测必须从 peak_idx + 1 开始
                    last_peak_idx = peak_idx
                    i = peak_idx + 1
                    
                    print(f"      ✅ 检测到投料: Valley={records[valley_idx]['time']}, Peak={records[peak_idx]['time']}, Added={total_added:.1f}kg")
                else:
                    # 没超过阈值，可能是小波动，继续
                    i += 1
            else:
                i += 1
                
        return events

    def _save_feeding_records(self, points: List[Point]):
        """保存到 InfluxDB"""
        try:
            write_api = self.history_service.client.write_api(write_options=SYNCHRONOUS)
            write_api.write(bucket=settings.influx_bucket, record=points)
            print(f"💾 已保存 {len(points)} 条投料记录")
        except Exception as e:
            print(f"❌ 保存投料记录失败: {e}")

# 单例导出
feeding_service = FeedingAnalysisService()
