# ============================================================
# 文件说明: feeding_analysis_service.py - 投料分析服务 v6.0
# ============================================================
# 核心功能:
# 1. 滑动窗口(可配置, 默认36样本)维护7组料仓的重量序列
# 2. 每N次轮询计算一次(可配置, 默认12次): 显示下料速度(存DB)
# 3. 投料总量累计计算: 逐点有效下降累加 + 上料期间缓存补偿(存DB)
# 窗口大小和计算间隔通过 .env FEEDING_WINDOW_SIZE / FEEDING_CALC_INTERVAL 配置
# 4. 上料记录检测(去抖动状态机, 存DB, 支持45分钟合并)
# ============================================================
# 调用关系:
#   polling_service._update_latest_data()
#       -> feeding_analysis_service.push_sample(device_id, weight, timestamp)
#       -> 每12次触发 _on_window_tick()
#       -> 计算速度 / 累计量 / 上料记录
# ============================================================
# 方法列表:
# 1. restore_from_db()            - 启动时还原投料总量
# 2. push_sample()                - 每次轮询推入样本
# 3. _on_window_tick()            - 每12次触发计算
# 4. _calc_display_feed_rate()    - 显示下料速度
# 5. _calc_feeding_total()        - 投料总量增量 (逐点累加 + 缓存补偿)
# 6. _update_loading_state()      - 上料检测状态机
# 7. _save_loading_record()       - 上料记录写入/合并
# 8. get_display_feed_rate()      - 查询显示下料速度
# 9. get_feeding_total()          - 查询投料总量
# 10. get_all_feeding_data()      - 查询所有料仓数据快照
# ============================================================

import logging
from collections import deque
from datetime import datetime, timezone
from typing import Dict, List, Optional, NamedTuple

from influxdb_client import Point
from influxdb_client.client.write_api import SYNCHRONOUS

from app.core.influxdb import get_influx_client
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ============================================================
# 配置常量 (不受算法影响的静态值)
# ============================================================
# 抖动死区阈值 (kg) - 相邻两点差值在此范围内视为不变
DEAD_ZONE_KG = 0.01

# 有效重量下限 (kg) - 低于此值视为料仓空或传感器异常
MIN_VALID_WEIGHT = 10.0

# 上料记录去抖动: 连续上升/下降次数阈值
LOADING_DEBOUNCE_COUNT = 3

# 上料记录合并: 两次上料间隔小于此时间 (秒) 则合并
LOADING_MERGE_INTERVAL_S = 45 * 60  # 45 分钟

# 7 个有称重传感器的料仓 (排除 no_hopper_1/2)
HOPPER_DEVICES: List[str] = [
    "short_hopper_1",
    "short_hopper_2",
    "short_hopper_3",
    "short_hopper_4",
    "long_hopper_1",
    "long_hopper_2",
    "long_hopper_3",
]


# ============================================================
# 数据结构
# ============================================================
class WeightSample(NamedTuple):
    """单次重量采样"""
    weight: float       # kg
    timestamp: datetime  # 带时区


class LoadingState:
    """单个料仓的上料检测状态机"""
    def __init__(self):
        self.is_loading: bool = False
        self.consecutive_rise: int = 0
        self.consecutive_fall: int = 0
        self.loading_start_ts: Optional[datetime] = None
        self.min_weight: float = 0.0
        self.max_weight: float = 0.0


# ============================================================
# 主服务类
# ============================================================
class FeedingAnalysisService:
    """
    投料分析服务 v6.0

    每个料仓(7组)维护:
    - 滑动窗口 deque(maxlen=_window_size) 存放 (weight, timestamp)
    - 轮询计数器 (每 _calc_interval 次触发计算)
    - 显示下料速度 (kg/h, 可负, 存DB + 推WS)
    - 缓存下料量 (kg, 上一次正常窗口的逐点有效下降量, 仅内存)
    - 投料总量累计 (kg, 存DB)
    - 上料检测状态机

    算法参数通过 .env 动态配置:
      FEEDING_WINDOW_SIZE  = 滑动窗口大小 (默认 36)
      FEEDING_CALC_INTERVAL= 计算触发间隔 (默认 12)
    """

    def __init__(self):
        # 1. 从 settings 动态读取算法参数 (settings 单例在进程启动时加载一次)
        self._window_size: int = settings.feeding_window_size
        self._calc_interval: int = min(
            settings.feeding_calc_interval, self._window_size
        )

        # 2. 滑动窗口: deque(maxlen=_window_size) 存放 WeightSample
        self._windows: Dict[str, deque] = {
            dev: deque(maxlen=self._window_size) for dev in HOPPER_DEVICES
        }

        # 3. 轮询计数器
        self._poll_count: Dict[str, int] = {
            dev: 0 for dev in HOPPER_DEVICES
        }

        # 3. 显示下料速度 (kg/h, 可负)
        self._display_feed_rate: Dict[str, float] = {
            dev: 0.0 for dev in HOPPER_DEVICES
        }

        # 4. 缓存下料量 (kg): 上一次正常窗口(非上料)的逐点有效下降累加值
        #    上料期间用此值补偿, 避免遗漏下料消耗
        self._cached_drop: Dict[str, float] = {
            dev: 0.0 for dev in HOPPER_DEVICES
        }

        # 5. 投料总量 (kg, 启动时从DB还原)
        self._feeding_total: Dict[str, float] = {
            dev: 0.0 for dev in HOPPER_DEVICES
        }

        # 6. 上料检测状态机
        self._loading_state: Dict[str, LoadingState] = {
            dev: LoadingState() for dev in HOPPER_DEVICES
        }

        self._restored = False

    # ----------------------------------------------------------
    # 1. 启动时还原投料总量
    # ----------------------------------------------------------
    async def restore_from_db(self):
        """从 InfluxDB last() 还原7个投料总量, 重启后不清零"""
        try:
            client = get_influx_client()
            query_api = client.query_api()
            bucket = settings.influx_bucket

            for dev in HOPPER_DEVICES:
                query = f'''
from(bucket: "{bucket}")
    |> range(start: -90d)
    |> filter(fn: (r) => r["_measurement"] == "feeding_cumulative")
    |> filter(fn: (r) => r["device_id"] == "{dev}")
    |> filter(fn: (r) => r["_field"] == "feeding_total")
    |> last()
'''
                result = query_api.query(query)
                for table in result:
                    for record in table.records:
                        val = float(record.get_value() or 0.0)
                        self._feeding_total[dev] = val
                        logger.info(f"[Feeding] {dev} 投料总量还原: {val:.1f} kg")

            self._restored = True
            logger.info("[Feeding] 投料总量还原完成")
        except Exception as e:
            logger.error(f"[Feeding] 还原投料总量失败: {e}", exc_info=True)

    # ----------------------------------------------------------
    # 2. 每次轮询推入样本 (由 polling_service 调用)
    # ----------------------------------------------------------
    def push_sample(self, device_id: str, weight: float, timestamp: datetime):
        """
        每次 PLC 轮询后调用, 推入重量样本到滑动窗口.
        同时驱动上料检测状态机(逐点检测, 不等窗口满).
        每 CALC_INTERVAL(12) 次触发速度和投料总量计算.
        """
        if device_id not in HOPPER_DEVICES:
            return

        if weight < MIN_VALID_WEIGHT:
            return

        sample = WeightSample(weight=weight, timestamp=timestamp)
        window = self._windows[device_id]

        # 逐点驱动上料检测状态机 (不等窗口, 实时检测)
        if len(window) > 0:
            prev_sample = window[-1]
            self._update_loading_state(device_id, prev_sample, sample)

        window.append(sample)
        self._poll_count[device_id] += 1

        # 每 _calc_interval 次触发计算
        if self._poll_count[device_id] >= self._calc_interval:
            self._poll_count[device_id] = 0
            self._on_window_tick(device_id)

    # ----------------------------------------------------------
    # 3. 窗口触发计算 (每 _calc_interval 次轮询)
    # ----------------------------------------------------------
    def _on_window_tick(self, device_id: str):
        """每 _calc_interval 次轮询触发: 计算显示下料速度 + 投料总量"""
        window = self._windows[device_id]

        if len(window) < 2:
            return

        # 3.1 计算显示下料速度 (整个窗口首尾差)
        self._calc_display_feed_rate(device_id, window)

        # 3.2 计算投料总量增量 (逐点累加 + 上料期间缓存补偿)
        self._calc_feeding_total(device_id, window)

        # 3.3 写显示下料速度 + 投料总量到 InfluxDB
        self._write_cumulative_point(device_id, window[-1].timestamp)

    # ----------------------------------------------------------
    # 3.1 显示下料速度: 窗口首尾差 / 总时间
    # ----------------------------------------------------------
    def _calc_display_feed_rate(self, device_id: str, window: deque):
        """显示下料速度 = (首重量 - 尾重量) * 3600 / 总时间(秒)
        可正可负: 正=下料, 负=上料
        """
        w_first = window[0].weight
        w_last = window[-1].weight
        time_span_s = (window[-1].timestamp - window[0].timestamp).total_seconds()

        if time_span_s <= 0:
            return

        # 先乘后除, 防止精度丢失
        self._display_feed_rate[device_id] = round(
            (w_first - w_last) * 3600 / time_span_s, 2
        )

    # ----------------------------------------------------------
    # 3.2 投料总量: 逐点有效下降累加 + 上料期间缓存补偿
    # ----------------------------------------------------------
    def _calc_feeding_total(self, device_id: str, window: deque):
        """
        取最近 _calc_interval 个样本计算投料总量增量.

        算法:
        1. 对最近12个样本逐点比较, 累加所有有效下降量
           (w[i] - w[i+1] > DEAD_ZONE_KG 视为有效下降)
        2. 两态判断 (绑定上料状态机):
           - 非上料状态(is_loading=False): 用逐点累加值, 同时更新缓存
           - 上料状态(is_loading=True): 整个窗口用缓存值补偿
             (上料期间窑仍在消耗料, 但称重全是上升, 用缓存补偿遗漏)
        3. 投料总量只增不减
        """
        samples = list(window)
        # 取最近 _calc_interval 个样本 (不足时取全部)
        recent = samples[-self._calc_interval:] if len(samples) >= self._calc_interval else samples

        if len(recent) < 2:
            return

        is_loading = self._loading_state[device_id].is_loading

        if not is_loading:
            # 正常状态: 逐点累加有效下降量
            current_drop = 0.0
            for i in range(len(recent) - 1):
                drop = recent[i].weight - recent[i + 1].weight
                if drop > DEAD_ZONE_KG:
                    current_drop += drop

            # 更新缓存 (记住正常窗口的下料量)
            self._cached_drop[device_id] = round(current_drop, 2)
            increment = current_drop
        else:
            # 上料状态: 整个窗口用缓存补偿
            increment = self._cached_drop[device_id]

        # 投料总量只增不减
        if increment > 0:
            self._feeding_total[device_id] = round(
                self._feeding_total[device_id] + increment, 2
            )

    # ----------------------------------------------------------
    # 4. 上料记录状态机 (逐点驱动)
    # ----------------------------------------------------------
    def _update_loading_state(
        self, device_id: str, prev: WeightSample, curr: WeightSample
    ):
        """
        逐点检测上料/停止上料:
        - 连续上升 > LOADING_DEBOUNCE_COUNT: 触发上料开始
        - 连续下降 > LOADING_DEBOUNCE_COUNT: 触发上料结束
        - 上料结束时生成记录, 查DB合并(45分钟内)或新建
        """
        state = self._loading_state[device_id]
        diff = curr.weight - prev.weight

        if diff > DEAD_ZONE_KG:
            # 上升
            state.consecutive_rise += 1
            state.consecutive_fall = 0
        elif diff < -DEAD_ZONE_KG:
            # 下降
            state.consecutive_fall += 1
            state.consecutive_rise = 0
        else:
            # 在死区内, 不重置计数 (允许微小抖动穿插)
            pass

        # 状态转换: 空闲 -> 上料
        if not state.is_loading and state.consecutive_rise >= LOADING_DEBOUNCE_COUNT:
            state.is_loading = True
            state.loading_start_ts = prev.timestamp
            state.min_weight = prev.weight
            state.max_weight = curr.weight
            state.consecutive_rise = 0
            logger.info(
                f"[Feeding] {device_id} 上料开始 "
                f"| 时间: {prev.timestamp.isoformat()} "
                f"| 最低重量: {state.min_weight:.1f} kg"
            )

        # 上料中: 持续更新最高/最低重量
        if state.is_loading:
            if curr.weight > state.max_weight:
                state.max_weight = curr.weight
            if curr.weight < state.min_weight:
                state.min_weight = curr.weight

        # 状态转换: 上料 -> 停止
        if state.is_loading and state.consecutive_fall >= LOADING_DEBOUNCE_COUNT:
            loading_amount = state.max_weight - state.min_weight
            loading_end_ts = curr.timestamp

            logger.info(
                f"[Feeding] {device_id} 上料结束 "
                f"| 上料量: {loading_amount:.1f} kg "
                f"| 最低: {state.min_weight:.1f} -> 最高: {state.max_weight:.1f} "
                f"| 时间: {state.loading_start_ts.isoformat()} ~ {loading_end_ts.isoformat()}"
            )

            # 写入或合并上料记录
            if loading_amount > 0:
                self._save_loading_record(
                    device_id=device_id,
                    amount=loading_amount,
                    min_weight=state.min_weight,
                    max_weight=state.max_weight,
                    start_ts=state.loading_start_ts,
                    end_ts=loading_end_ts,
                )

            # 重置状态
            state.is_loading = False
            state.consecutive_rise = 0
            state.consecutive_fall = 0
            state.loading_start_ts = None
            state.min_weight = 0.0
            state.max_weight = 0.0

    # ----------------------------------------------------------
    # 5. 上料记录写入 (合并或新建)
    # ----------------------------------------------------------
    def _save_loading_record(
        self,
        device_id: str,
        amount: float,
        min_weight: float,
        max_weight: float,
        start_ts: datetime,
        end_ts: datetime,
    ):
        """
        写入上料记录到 InfluxDB (measurement=feeding_records).
        如果与最近一条记录间隔 < 45分钟, 则合并(累加 amount).
        """
        try:
            client = get_influx_client()
            bucket = settings.influx_bucket

            # 查询最近一条上料记录
            query_api = client.query_api()
            query = f'''
from(bucket: "{bucket}")
    |> range(start: -2h)
    |> filter(fn: (r) => r["_measurement"] == "feeding_records")
    |> filter(fn: (r) => r["device_id"] == "{device_id}")
    |> filter(fn: (r) => r["_field"] == "amount")
    |> last()
'''
            last_record_ts = None
            last_record_amount = 0.0

            result = query_api.query(query)
            for table in result:
                for record in table.records:
                    last_record_ts = record.get_time()
                    last_record_amount = float(record.get_value() or 0.0)

            should_merge = False
            if last_record_ts is not None:
                # 确保时区一致再比较
                compare_ts = start_ts
                if compare_ts.tzinfo is None:
                    compare_ts = compare_ts.replace(tzinfo=timezone.utc)
                gap = abs((compare_ts - last_record_ts).total_seconds())

                if gap < LOADING_MERGE_INTERVAL_S:
                    should_merge = True

            if should_merge:
                # 合并: 使用旧记录时间戳, 累加上料量
                merged_amount = round(last_record_amount + amount, 2)
                write_ts = last_record_ts
                logger.info(
                    f"[Feeding] {device_id} 合并上料记录 "
                    f"| 旧: {last_record_amount:.1f} + 新: {amount:.1f} = {merged_amount:.1f} kg"
                )
                final_amount = merged_amount
            else:
                write_ts = start_ts
                final_amount = round(amount, 2)

            # 写入记录
            p = (
                Point("feeding_records")
                .tag("device_id", device_id)
                .field("amount", final_amount)
                .field("min_weight", round(min_weight, 2))
                .field("max_weight", round(max_weight, 2))
                .field("merged", should_merge)
                .time(write_ts)
            )
            write_api = client.write_api(write_options=SYNCHRONOUS)
            write_api.write(bucket=bucket, record=p)

            logger.info(
                f"[Feeding] {device_id} 上料记录已写入 "
                f"| amount={final_amount:.1f} kg | merged={should_merge}"
            )
        except Exception as e:
            logger.error(f"[Feeding] 写入上料记录失败 ({device_id}): {e}", exc_info=True)

    # ----------------------------------------------------------
    # 6. 写 InfluxDB: 显示下料速度 + 投料总量 (合并为一条写入)
    # ----------------------------------------------------------
    def _write_cumulative_point(self, device_id: str, timestamp: datetime):
        """写显示下料速度和投料总量到 feeding_cumulative measurement"""
        try:
            p = (
                Point("feeding_cumulative")
                .tag("device_id", device_id)
                .field("display_feed_rate", self._display_feed_rate[device_id])
                .field("feeding_total", self._feeding_total[device_id])
                .time(timestamp)
            )
            client = get_influx_client()
            write_api = client.write_api(write_options=SYNCHRONOUS)
            write_api.write(bucket=settings.influx_bucket, record=p)
        except Exception as e:
            logger.error(f"[Feeding] 写 InfluxDB 失败 ({device_id}): {e}", exc_info=True)

    # ----------------------------------------------------------
    # 7. 查询接口 (供 API / WebSocket 推送使用)
    # ----------------------------------------------------------
    def get_display_feed_rate(self, device_id: str) -> float:
        """返回显示下料速度 (kg/h, 可负)"""
        return self._display_feed_rate.get(device_id, 0.0)

    def get_feeding_total(self, device_id: str) -> float:
        """返回投料总量 (kg)"""
        return self._feeding_total.get(device_id, 0.0)

    def get_all_feeding_data(self) -> Dict[str, dict]:
        """返回所有料仓的投料分析数据快照 (供 WebSocket 推送)"""
        result = {}
        for dev in HOPPER_DEVICES:
            result[dev] = {
                "display_feed_rate": self._display_feed_rate[dev],
                "cached_drop": self._cached_drop[dev],
                "feeding_total": self._feeding_total[dev],
                "is_loading": self._loading_state[dev].is_loading,
            }
        return result


# ============================================================
# 全局单例
# ============================================================
feeding_analysis_service = FeedingAnalysisService()
