# ============================================================
# 文件说明: daily_summary_service.py - 日汇总数据计算与存储服务
# ============================================================
# 公开方法:
#  1. calculate_and_store_daily_summary()  - 计算并存储指定日期的汇总数据
#  2. check_and_fill_missing_dates()       - 检测并补全缺失的日期数据
#  3. get_available_dates()                - 获取已有的日期列表
#  4. get_daily_summary()                  - 查询日汇总数据
#  5. force_recalculate_range()            - 强制重算指定日期范围
#  6. get_all_runtime_inspect()            - 诊断: 查看全部设备运行时长数据
# 内部方法:
#  6. _query_first_last_value()            - 查询首末值 (ImpEp/total_flow)
#  7. _calc_runtime_count()                - 计算运行时长 (elapsed 算法)
#  8. _calc_electricity_point()            - 通用电量 Point
#  9. _calc_roller_kiln_electricity_point() - 辊道窑温区电量 Point
# 10. _calc_gas_point()                    - 燃气消耗 Point
# 11. _calc_roller_kiln_total_point()      - 辊道窑总表 Point (温区汇总)
# 12. _calc_scr_pump_electricity_point()   - SCR 氨水泵电量 Point
# 13. _calc_feeding_point()                - 投料量 Point
# ============================================================

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from influxdb_client import Point

from app.core.influxdb import build_point, get_influx_client, write_points_batch
from app.tools.timezone_tools import BEIJING_TZ, to_beijing
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# 单例实例
_instance: Optional["DailySummaryService"] = None


# ============================================================
# 设备配置表
# ============================================================

# 料仓设备列表 (回转窑)
HOPPER_DEVICES = [
    {"device_id": "short_hopper_1", "device_type": "hopper"},
    {"device_id": "short_hopper_2", "device_type": "hopper"},
    {"device_id": "short_hopper_3", "device_type": "hopper"},
    {"device_id": "short_hopper_4", "device_type": "hopper"},
    {"device_id": "no_hopper_1",    "device_type": "hopper"},
    {"device_id": "no_hopper_2",    "device_type": "hopper"},
    {"device_id": "long_hopper_1",  "device_type": "hopper"},
    {"device_id": "long_hopper_2",  "device_type": "hopper"},
    {"device_id": "long_hopper_3",  "device_type": "hopper"},
]

# 辊道窑温区列表 (zone1~zone6, 在 sensor_data 中对应 module_tag=zone1_meter 等)
ROLLER_KILN_ZONES = [
    {"device_id": "zone1", "device_type": "roller_kiln_zone", "module_tag": "zone1_meter"},
    {"device_id": "zone2", "device_type": "roller_kiln_zone", "module_tag": "zone2_meter"},
    {"device_id": "zone3", "device_type": "roller_kiln_zone", "module_tag": "zone3_meter"},
    {"device_id": "zone4", "device_type": "roller_kiln_zone", "module_tag": "zone4_meter"},
    {"device_id": "zone5", "device_type": "roller_kiln_zone", "module_tag": "zone5_meter"},
    {"device_id": "zone6", "device_type": "roller_kiln_zone", "module_tag": "zone6_meter"},
]

# SCR 设备列表
SCR_DEVICES = [
    {"device_id": "scr_1", "device_type": "scr"},
    {"device_id": "scr_2", "device_type": "scr"},
]

# 风机设备列表
FAN_DEVICES = [
    {"device_id": "fan_1", "device_type": "fan"},
    {"device_id": "fan_2", "device_type": "fan"},
]

# 辊道窑总表 (zone1~zone6 汇总)
ROLLER_KILN_TOTAL = {
    "device_id": "roller_kiln_total",
    "device_type": "roller_kiln_total",
}

# SCR 氨水泵设备列表 (独立电表, 通过 module_tag=meter 从 scr_1/scr_2 中筛选)
SCR_PUMP_DEVICES = [
    {"device_id": "scr_1_pump", "device_type": "scr_pump", "src_device_id": "scr_1", "module_tag": "meter"},
    {"device_id": "scr_2_pump", "device_type": "scr_pump", "src_device_id": "scr_2", "module_tag": "meter"},
]

# 最小运行功率阈值 (kW)，低于此值认为设备未运行
RUNTIME_POWER_THRESHOLD = 1.0

# 独立设备运行阈值 (kW) - 覆盖默认值
# SCR 氨水泵: 36W = 0.036kW
# 风机: 500W = 0.5kW
DEVICE_RUNTIME_THRESHOLDS = {
    "scr_1": 0.036,
    "scr_2": 0.036,
    "fan_1": 0.5,
    "fan_2": 0.5,
}


class DailySummaryService:
    """日汇总数据计算与存储服务（单例模式）"""

    def __init__(self):
        self._client = None
        self._query_api = None
        self.bucket = settings.influx_bucket
        self.org = settings.influx_org
        # 从配置读取实际轮询间隔 (秒), 用于 elapsed() 断连阈值计算
        self._polling_interval = settings.plc_poll_interval
        # 移动平均窗口大小, 用于消除阈值边界抖动 (防抖)
        self._smoothing_window = 3
        # 小时补齐阈值 (秒): 某小时内运行时长 >= 此值则补齐为 3600s (1h)
        # 3240 = 0.9 * 3600, 即每小时运行 >= 54 分钟计为整小时
        self._hour_round_threshold = 3240

    @property
    def client(self):
        if self._client is None:
            self._client = get_influx_client()
        return self._client

    @property
    def query_api(self):
        return self.client.query_api()

    # ------------------------------------------------------------
    # 1. calculate_and_store_daily_summary() - 计算并存储日汇总
    # ------------------------------------------------------------
    def calculate_and_store_daily_summary(self, target_dt: datetime) -> Dict[str, Any]:
        """计算并存储指定日期的汇总数据

        target_dt 代表的是"北京时间的哪一天"，本方法会以北京午夜 0:00
        作为天边界，转换为 UTC 后查询 InfluxDB。

        Args:
            target_dt: 目标日期 (UTC datetime，但代表的是北京日期)

        Returns:
            {
                "date": "2026-01-26",
                "success": True,
                "devices_processed": 20,
                "points_written": 80
            }
        """
        # 将 target_dt 转换为北京时间，取北京日期边界
        target_bj = to_beijing(target_dt)
        date_label = target_bj.strftime("%Y-%m-%d")
        date_str = target_bj.strftime("%Y%m%d")

        # 北京当天 0:00 和次日 0:00，转换为 UTC 用于 InfluxDB 查询
        day_start_bj = target_bj.replace(hour=0, minute=0, second=0, microsecond=0)
        day_start = day_start_bj.astimezone(timezone.utc)
        day_end = (day_start_bj + timedelta(days=1)).astimezone(timezone.utc)

        logger.info("[DailySummary] 开始计算日汇总: %s", date_label)

        all_points: List[Point] = []
        devices_processed = 0

        # 1. 计算料仓电量 + 投料
        for dev in HOPPER_DEVICES:
            device_id = dev["device_id"]
            device_type = dev["device_type"]

            elec_point = self._calc_electricity_point(
                device_id, device_type, date_str, day_start, day_end,
                src_device_id=device_id, src_device_type="rotary_kiln"
            )
            if elec_point:
                all_points.append(elec_point)

            feeding_point = self._calc_feeding_point(
                device_id, device_type, date_str, day_start, day_end
            )
            if feeding_point:
                all_points.append(feeding_point)

            devices_processed += 1

        # 2. 计算辊道窑温区电量 (同时收集中间结果供 step5 汇总)
        roller_zone_stats = []
        for zone in ROLLER_KILN_ZONES:
            device_id = zone["device_id"]
            device_type = zone["device_type"]
            module_tag = zone["module_tag"]

            elec_point, zone_stats = self._calc_roller_kiln_electricity_point(
                device_id, device_type, date_str, day_start, day_end, module_tag
            )
            if elec_point:
                all_points.append(elec_point)
            if zone_stats:
                roller_zone_stats.append(zone_stats)

            devices_processed += 1

        # 3. 计算 SCR 电量 + 燃气
        for dev in SCR_DEVICES:
            device_id = dev["device_id"]
            device_type = dev["device_type"]

            elec_point = self._calc_electricity_point(
                device_id, device_type, date_str, day_start, day_end,
                src_device_id=device_id, src_device_type="scr"
            )
            if elec_point:
                all_points.append(elec_point)

            gas_point = self._calc_gas_point(
                device_id, device_type, date_str, day_start, day_end
            )
            if gas_point:
                all_points.append(gas_point)

            devices_processed += 1

        # 4. 计算风机电量
        for dev in FAN_DEVICES:
            device_id = dev["device_id"]
            device_type = dev["device_type"]

            elec_point = self._calc_electricity_point(
                device_id, device_type, date_str, day_start, day_end,
                src_device_id=device_id, src_device_type="fan"
            )
            if elec_point:
                all_points.append(elec_point)

            devices_processed += 1

        # 5. 计算辊道窑总表 (从 step2 的温区中间结果汇总, 无需重复查询)
        total_point = self._calc_roller_kiln_total_point(
            date_str, day_start, roller_zone_stats
        )
        if total_point:
            all_points.append(total_point)
        devices_processed += 1

        # 6. 计算 SCR 氨水泵电量 (独立电表, 通过 module_tag=meter 筛选)
        for dev in SCR_PUMP_DEVICES:
            device_id = dev["device_id"]
            device_type = dev["device_type"]
            src_device_id = dev["src_device_id"]
            module_tag = dev["module_tag"]

            elec_point = self._calc_scr_pump_electricity_point(
                device_id, device_type, date_str, day_start, day_end,
                src_device_id, module_tag
            )
            if elec_point:
                all_points.append(elec_point)

            devices_processed += 1

        # 7. 批量写入
        points_written = 0
        if all_points:
            success, err = write_points_batch(all_points)
            if success:
                points_written = len(all_points)
                logger.info("[DailySummary] 日汇总写入完成: %s, %s 个数据点", date_label, points_written)
            else:
                logger.error("[DailySummary] 日汇总写入失败: %s, %s", date_label, err)
                return {
                    "date": date_label,
                    "success": False,
                    "error": err,
                    "devices_processed": devices_processed,
                    "points_written": 0,
                }
        else:
            logger.warning("[DailySummary] 日汇总: %s 无有效数据点", date_label)

        return {
            "date": date_label,
            "success": True,
            "devices_processed": devices_processed,
            "points_written": points_written,
        }

    # ------------------------------------------------------------
    # 2. check_and_fill_missing_dates() - 检测并补全缺失日期
    # ------------------------------------------------------------
    def check_and_fill_missing_dates(self, end_dt: datetime) -> Dict[str, Any]:
        """检测并补全缺失的日期数据

        日期列表基于北京时间自然日。

        Args:
            end_dt: 检查的结束日期 (UTC)

        Returns:
            {
                "checked_range": "2026-01-01 ~ 2026-01-26",
                "existing_dates": [...],
                "missing_dates": [...],
                "filled_dates": [...],
                "total_filled": 1
            }
        """
        existing_dates = self.get_available_dates()

        # 将 end_dt 转换为北京日期
        end_bj = to_beijing(end_dt)

        if not existing_dates:
            # 没有任何数据，从 30 天前开始
            start_bj = end_bj - timedelta(days=30)
        else:
            first_date_str = existing_dates[0]  # YYYYMMDD
            start_bj = datetime.strptime(first_date_str, "%Y%m%d").replace(tzinfo=BEIJING_TZ)

        # 生成期望的日期列表 (北京自然日)
        expected_dates = []
        cur = start_bj.replace(hour=0, minute=0, second=0, microsecond=0)
        end = end_bj.replace(hour=0, minute=0, second=0, microsecond=0)
        while cur <= end:
            expected_dates.append(cur.strftime("%Y%m%d"))
            cur += timedelta(days=1)

        existing_set = set(existing_dates)
        missing_dates = [d for d in expected_dates if d not in existing_set]

        logger.info("[DailySummary] 检测缺失日期: 共 %s 天, 缺失 %s 天", len(expected_dates), len(missing_dates))

        filled_dates = []
        for date_str in missing_dates:
            # 解析为北京日期，传给 calculate_and_store_daily_summary
            target_dt = datetime.strptime(date_str, "%Y%m%d").replace(tzinfo=BEIJING_TZ)
            result = self.calculate_and_store_daily_summary(target_dt)
            if result.get("success") and result.get("points_written", 0) > 0:
                filled_dates.append(date_str)

        return {
            "checked_range": f"{start_bj.strftime('%Y-%m-%d')} ~ {end_bj.strftime('%Y-%m-%d')}",
            "existing_dates": existing_dates,
            "missing_dates": missing_dates,
            "filled_dates": filled_dates,
            "total_filled": len(filled_dates),
        }

    # ------------------------------------------------------------
    # 3. get_available_dates() - 获取已有日期列表
    # ------------------------------------------------------------
    def get_available_dates(self) -> List[str]:
        """获取 daily_summary 中已有的日期列表 (YYYYMMDD, 升序)"""
        query = f'''
        from(bucket: "{self.bucket}")
            |> range(start: -3650d)
            |> filter(fn: (r) => r["_measurement"] == "daily_summary")
            |> keep(columns: ["date"])
            |> distinct(column: "date")
        '''
        try:
            result = self.query_api.query(query)
            dates = set()
            for table in result:
                for record in table.records:
                    date_val = record.values.get("date") or record.get_value()
                    if date_val:
                        dates.add(str(date_val))
            return sorted(dates)
        except Exception as e:
            logger.error("[DailySummary] 获取可用日期失败: %s", e, exc_info=True)
            return []

    # ------------------------------------------------------------
    # 4. get_daily_summary() - 查询日汇总数据
    # ------------------------------------------------------------
    def get_daily_summary(
        self,
        device_id: str,
        metric_type: str,
        start_date: datetime,
        end_date: datetime,
    ) -> List[Dict[str, Any]]:
        """查询指定设备、指标类型、时间范围的日汇总数据

        Args:
            device_id:   设备ID
            metric_type: 指标类型 (electricity, gas, feeding, runtime)
            start_date:  开始日期 (带时区, 北京时间)
            end_date:    结束日期 (带时区, 北京时间)

        Returns:
            [{"date": "20260126", "start_reading": ..., "end_reading": ..., "consumption": ..., ...}]
        """
        # 结束时间向后延一天，确保包含 end_date 当天
        range_end = end_date + timedelta(days=1)

        query = f'''
        from(bucket: "{self.bucket}")
            |> range(start: {start_date.isoformat()}, stop: {range_end.isoformat()})
            |> filter(fn: (r) => r["_measurement"] == "daily_summary")
            |> filter(fn: (r) => r["device_id"] == "{device_id}")
            |> filter(fn: (r) => r["metric_type"] == "{metric_type}")
            |> pivot(rowKey:["_time", "device_id", "metric_type", "date"],
                     columnKey: ["_field"],
                     valueColumn: "_value")
        '''
        try:
            result = self.query_api.query(query)
            records = []
            for table in result:
                for record in table.records:
                    records.append({
                        "date":             record.values.get("date", ""),
                        "start_reading":    record.values.get("start_reading", 0.0),
                        "end_reading":      record.values.get("end_reading", 0.0),
                        "consumption":      record.values.get("consumption", 0.0),
                        "runtime_hours":    record.values.get("runtime_hours", 0.0),
                        "feeding_amount":   record.values.get("feeding_amount", 0.0),
                        "gas_consumption":  record.values.get("gas_consumption", 0.0),
                    })
            # 按日期升序排列
            records.sort(key=lambda r: r["date"])
            return records
        except Exception as e:
            logger.error("[DailySummary] 查询日汇总失败: %s", e, exc_info=True)
            return []

    # ------------------------------------------------------------
    # 6. get_all_runtime_inspect() - 诊断: 查看全部设备运行时长数据
    # ------------------------------------------------------------
    def get_all_runtime_inspect(
        self,
        start_date: str,
        end_date: str,
    ) -> Dict[str, Any]:
        """查询全部设备的 daily_summary 运行时长数据 (诊断用)

        Args:
            start_date: 开始日期 "YYYY-MM-DD"
            end_date:   结束日期 "YYYY-MM-DD"

        Returns:
            {
                "date_range": {"start": "2026-03-01", "end": "2026-03-04"},
                "total_records": 42,
                "by_date": {
                    "2026-03-01": [
                        {"device_id": "short_hopper_1", "device_type": "hopper",
                         "metric_type": "electricity",
                         "runtime_hours": 12.5, "consumption": 45.6,
                         "start_reading": 100.0, "end_reading": 145.6},
                        ...
                    ],
                    ...
                }
            }
        """
        # 1. 解析时间范围 (北京时间)
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=BEIJING_TZ)
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=BEIJING_TZ)
        # 结束时间向后延一天, 确保包含 end_date 当天
        range_end = end_dt + timedelta(days=1)

        # 2. Flux 查询: 查全部 daily_summary 数据, 不限设备和指标类型
        query = f'''
        from(bucket: "{self.bucket}")
            |> range(start: {start_dt.isoformat()}, stop: {range_end.isoformat()})
            |> filter(fn: (r) => r["_measurement"] == "daily_summary")
            |> pivot(rowKey:["_time", "device_id", "device_type", "metric_type", "date"],
                     columnKey: ["_field"],
                     valueColumn: "_value")
        '''

        try:
            result = self.query_api.query(query)
        except Exception as e:
            logger.error("[DailySummary] runtime-inspect 查询失败: %s", e, exc_info=True)
            return {
                "date_range": {"start": start_date, "end": end_date},
                "total_records": 0,
                "by_date": {},
                "error": str(e),
            }

        # 3. 遍历结果, 按日期分组 (date tag 为 YYYYMMDD, 转成 YYYY-MM-DD)
        by_date: Dict[str, list] = {}
        total_records = 0

        for table in result:
            for record in table.records:
                date_raw = record.values.get("date", "")
                # 转为可读日期
                if len(date_raw) == 8:
                    date_key = f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:8]}"
                else:
                    date_key = date_raw

                device_id = record.values.get("device_id", "")
                device_type = record.values.get("device_type", "")
                metric_type = record.values.get("metric_type", "")

                row = {
                    "device_id": device_id,
                    "device_type": device_type,
                    "metric_type": metric_type,
                    "runtime_hours": round(record.values.get("runtime_hours", 0.0) or 0.0, 4),
                    "consumption": round(record.values.get("consumption", 0.0) or 0.0, 4),
                    "start_reading": round(record.values.get("start_reading", 0.0) or 0.0, 4),
                    "end_reading": round(record.values.get("end_reading", 0.0) or 0.0, 4),
                    "feeding_amount": round(record.values.get("feeding_amount", 0.0) or 0.0, 4),
                    "gas_consumption": round(record.values.get("gas_consumption", 0.0) or 0.0, 4),
                }

                if date_key not in by_date:
                    by_date[date_key] = []
                by_date[date_key].append(row)
                total_records += 1

        # 4. 每个日期内按 device_id 排序
        for date_key in by_date:
            by_date[date_key].sort(key=lambda r: (r["metric_type"], r["device_id"]))

        # 5. 按日期排序输出
        sorted_by_date = dict(sorted(by_date.items()))

        return {
            "date_range": {"start": start_date, "end": end_date},
            "total_records": total_records,
            "by_date": sorted_by_date,
        }

    # ============================================================
    # 内部辅助方法
    # ============================================================

    def _query_first_last_value(
        self,
        field: str,
        device_id: str,
        day_start: datetime,
        day_end: datetime,
        extra_filter: str = "",
    ) -> tuple:
        """查询某天某字段的首值和尾值

        Returns:
            (first_value, last_value) 或 (None, None)
        """
        query = f'''
        from(bucket: "{self.bucket}")
            |> range(start: {day_start.isoformat()}, stop: {day_end.isoformat()})
            |> filter(fn: (r) => r["_measurement"] == "sensor_data")
            |> filter(fn: (r) => r["device_id"] == "{device_id}")
            |> filter(fn: (r) => r["_field"] == "{field}")
            {extra_filter}
        '''
        first_q = query + '|> first()'
        last_q  = query + '|> last()'

        first_val = None
        last_val  = None

        try:
            result = self.query_api.query(first_q)
            for table in result:
                for record in table.records:
                    first_val = record.get_value()
                    break
                if first_val is not None:
                    break
        except Exception as e:
            logger.warning("[DailySummary] 查询首值失败 (%s/%s): %s", device_id, field, e)

        try:
            result = self.query_api.query(last_q)
            for table in result:
                for record in table.records:
                    last_val = record.get_value()
                    break
                if last_val is not None:
                    break
        except Exception as e:
            logger.warning("[DailySummary] 查询尾值失败 (%s/%s): %s", device_id, field, e)

        return (first_val, last_val)

    def _calc_runtime_count(
        self,
        device_id: str,
        day_start: datetime,
        day_end: datetime,
        field: str = "Pt",
        threshold: float = RUNTIME_POWER_THRESHOLD,
        extra_filter: str = "",
    ) -> float:
        """计算设备当天运行时长 (基于功率/流量阈值)

        算法: elapsed() 实际时差累加 + 小时补齐
        1. 对相邻数据点计算真实时间差 (elapsed, 单位秒)
        2. 只累加: 当前点 field > threshold (设备运行) AND elapsed <= max_gap (排除断连空洞)
        3. 按小时分窗 (window 1h), 每小时运行 >= 54 分钟 (0.9h) 则补齐为 60 分钟
        4. max_gap = polling_interval * 12 (默认 60s), 超过视为 PLC 断连或停机间隔

        优势:
        - 使用真实 timestamp 差值, 免疫轮询抖动
        - PLC 断连恢复后的空洞自动排除
        - 小时补齐消除边界效应, 全天运行设备精确显示 24.0h

        Args:
            device_id:    设备ID (sensor_data 中的 device_id)
            day_start:    当天起始时间 (UTC)
            day_end:      当天结束时间 (UTC)
            field:        判断运行的字段 (默认 "Pt")
            threshold:    运行阈值 (默认 RUNTIME_POWER_THRESHOLD)
            extra_filter: 额外 Flux 过滤条件 (如 module_tag)

        Returns:
            运行时长 (小时), 如 18.5
        """
        # max_gap: 相邻点时差超过此阈值视为断连/停机, 不计入运行时长
        # 取 12 倍轮询间隔, 即连续缺失 12 个点才认定为停机边界
        max_gap_seconds = self._polling_interval * 12

        query = f'''
        from(bucket: "{self.bucket}")
            |> range(start: {day_start.isoformat()}, stop: {day_end.isoformat()})
            |> filter(fn: (r) => r["_measurement"] == "sensor_data")
            |> filter(fn: (r) => r["device_id"] == "{device_id}")
            |> filter(fn: (r) => r["_field"] == "{field}")
            {extra_filter}
            |> movingAverage(n: {self._smoothing_window})
            |> elapsed(unit: 1s, columnName: "dt")
            |> filter(fn: (r) => r["_value"] > {threshold} and r["dt"] <= {max_gap_seconds})
            |> map(fn: (r) => ({{r with _value: float(v: r.dt)}}))
            |> window(every: 1h)
            |> sum()
            |> map(fn: (r) => ({{r with _value: if r._value >= {self._hour_round_threshold}.0 then 3600.0 else r._value}}))
            |> group()
            |> sum()
        '''
        try:
            result = self.query_api.query(query)
            total_seconds = 0.0
            for table in result:
                for record in table.records:
                    total_seconds = float(record.get_value() or 0)
                    break
                break
            return round(total_seconds / 3600.0, 2)
        except Exception as e:
            logger.warning("[DailySummary] 计算运行时长失败 (%s): %s", device_id, e)
            return 0.0

    def _calc_electricity_point(
        self,
        device_id: str,
        device_type: str,
        date_str: str,
        day_start: datetime,
        day_end: datetime,
        src_device_id: str,
        src_device_type: str,
    ) -> Optional[Point]:
        """计算电量汇总 Point (基于 ImpEp 累计值)"""
        first_val, last_val = self._query_first_last_value(
            field="ImpEp",
            device_id=src_device_id,
            day_start=day_start,
            day_end=day_end,
        )

        if first_val is None or last_val is None:
            return None

        # 处理仪表重置 (end < start)
        consumption = max(0.0, float(last_val) - float(first_val))

        # 计算运行时长 (统计 Pt > 阈值的数据点)
        threshold = DEVICE_RUNTIME_THRESHOLDS.get(src_device_id, RUNTIME_POWER_THRESHOLD)
        runtime_hours = self._calc_runtime_count(
            device_id=src_device_id,
            day_start=day_start,
            day_end=day_end,
            threshold=threshold,
        )

        return build_point(
            measurement="daily_summary",
            tags={
                "device_id":   device_id,
                "device_type": device_type,
                "date":        date_str,
                "metric_type": "electricity",
            },
            fields={
                "start_reading": float(first_val),
                "end_reading":   float(last_val),
                "consumption":   consumption,
                "runtime_hours": runtime_hours,
                "feeding_amount": 0.0,
                "gas_consumption": 0.0,
            },
            timestamp=day_start,
        )

    def _calc_roller_kiln_electricity_point(
        self,
        device_id: str,
        device_type: str,
        date_str: str,
        day_start: datetime,
        day_end: datetime,
        module_tag: str,
    ) -> tuple:
        """计算辊道窑温区电量 Point

        Returns:
            (Optional[Point], Optional[dict]) - Point 和中间统计数据
            stats_dict 包含 device_id, consumption, runtime_hours, first_val, last_val
            如果缺少数据则返回 (None, None)
        """
        extra_filter = f'|> filter(fn: (r) => r["module_tag"] == "{module_tag}")'
        first_val, last_val = self._query_first_last_value(
            field="ImpEp",
            device_id="roller_kiln_1",
            day_start=day_start,
            day_end=day_end,
            extra_filter=extra_filter,
        )

        if first_val is None or last_val is None:
            return (None, None)

        consumption = max(0.0, float(last_val) - float(first_val))

        # 计算运行时长 (通过 module_tag 筛选对应温区)
        runtime_hours = self._calc_runtime_count(
            device_id="roller_kiln_1",
            day_start=day_start,
            day_end=day_end,
            extra_filter=extra_filter,
        )

        stats = {
            "device_id": device_id,
            "consumption": consumption,
            "runtime_hours": runtime_hours,
            "first_val": float(first_val),
            "last_val": float(last_val),
        }

        point = build_point(
            measurement="daily_summary",
            tags={
                "device_id":   device_id,
                "device_type": device_type,
                "date":        date_str,
                "metric_type": "electricity",
            },
            fields={
                "start_reading":  float(first_val),
                "end_reading":    float(last_val),
                "consumption":    consumption,
                "runtime_hours":  runtime_hours,
                "feeding_amount": 0.0,
                "gas_consumption": 0.0,
            },
            timestamp=day_start,
        )
        return (point, stats)

    def _calc_gas_point(
        self,
        device_id: str,
        device_type: str,
        date_str: str,
        day_start: datetime,
        day_end: datetime,
    ) -> Optional[Point]:
        """计算燃气消耗 Point (基于 total_flow 累计值)"""
        first_val, last_val = self._query_first_last_value(
            field="total_flow",
            device_id=device_id,
            day_start=day_start,
            day_end=day_end,
        )

        if first_val is None or last_val is None:
            return None

        gas_consumption = max(0.0, float(last_val) - float(first_val))

        # 计算燃气运行时长 (基于 flow_rate > 0.01 的 elapsed 时差累加)
        runtime_hours = self._calc_runtime_count(
            device_id=device_id,
            day_start=day_start,
            day_end=day_end,
            field="flow_rate",
            threshold=0.01,
        )

        return build_point(
            measurement="daily_summary",
            tags={
                "device_id":   device_id,
                "device_type": device_type,
                "date":        date_str,
                "metric_type": "gas",
            },
            fields={
                "start_reading":   float(first_val),
                "end_reading":     float(last_val),
                "consumption":     gas_consumption,
                "runtime_hours":   runtime_hours,
                "feeding_amount":  0.0,
                "gas_consumption": gas_consumption,
            },
            timestamp=day_start,
        )

    def _calc_roller_kiln_total_point(
        self,
        date_str: str,
        day_start: datetime,
        zone_stats: List[Dict],
    ) -> Optional[Point]:
        """计算辊道窑总表 Point (zone1~zone6 电量汇总)

        从 step2 已计算的温区中间结果中提取 consumption 和 runtime_hours 汇总。
        首末读数取 zone1 的值 (代表性展示)。

        Args:
            zone_stats: step2 收集的温区统计列表, 每项含
                        device_id, consumption, runtime_hours, first_val, last_val
        """
        if not zone_stats:
            return None

        total_consumption = sum(z["consumption"] for z in zone_stats)

        # 取各温区运行时长的最大值 (辊道窑共用一条线, 最长温区代表整体)
        max_runtime = max(z["runtime_hours"] for z in zone_stats)

        # zone1 的首末读数作为代表
        zone1_stats = next(
            (z for z in zone_stats if z["device_id"] == "zone1"),
            zone_stats[0],
        )
        first_reading = zone1_stats["first_val"]
        last_reading = zone1_stats["last_val"]

        return build_point(
            measurement="daily_summary",
            tags={
                "device_id":   "roller_kiln_total",
                "device_type": "roller_kiln_total",
                "date":        date_str,
                "metric_type": "electricity",
            },
            fields={
                "start_reading":  first_reading,
                "end_reading":    last_reading,
                "consumption":    round(total_consumption, 2),
                "runtime_hours":  max_runtime,
                "feeding_amount": 0.0,
                "gas_consumption": 0.0,
            },
            timestamp=day_start,
        )

    def _calc_scr_pump_electricity_point(
        self,
        device_id: str,
        device_type: str,
        date_str: str,
        day_start: datetime,
        day_end: datetime,
        src_device_id: str,
        module_tag: str,
    ) -> Optional[Point]:
        """计算 SCR 氨水泵电量 Point (通过 module_tag 从父设备筛选电表数据)"""
        extra_filter = f'|> filter(fn: (r) => r["module_tag"] == "{module_tag}")'
        first_val, last_val = self._query_first_last_value(
            field="ImpEp",
            device_id=src_device_id,
            day_start=day_start,
            day_end=day_end,
            extra_filter=extra_filter,
        )

        if first_val is None or last_val is None:
            return None

        consumption = max(0.0, float(last_val) - float(first_val))

        # 计算运行时长 (SCR 氨水泵功率阈值 0.036 kW)
        threshold = DEVICE_RUNTIME_THRESHOLDS.get(src_device_id, 0.036)
        runtime_hours = self._calc_runtime_count(
            device_id=src_device_id,
            day_start=day_start,
            day_end=day_end,
            threshold=threshold,
            extra_filter=extra_filter,
        )

        return build_point(
            measurement="daily_summary",
            tags={
                "device_id":   device_id,
                "device_type": device_type,
                "date":        date_str,
                "metric_type": "electricity",
            },
            fields={
                "start_reading":  float(first_val),
                "end_reading":    float(last_val),
                "consumption":    consumption,
                "runtime_hours":  runtime_hours,
                "feeding_amount": 0.0,
                "gas_consumption": 0.0,
            },
            timestamp=day_start,
        )

    def _calc_feeding_point(
        self,
        device_id: str,
        device_type: str,
        date_str: str,
        day_start: datetime,
        day_end: datetime,
    ) -> Optional[Point]:
        """计算投料量 Point (使用 feeding_cumulative.feeding_total 的 spread)
        
        数据来源: feeding_analysis_service v6.0 写入的 feeding_cumulative measurement
        算法: spread(max - min) 得到当天投料总量的增量
        """
        query = f'''
        from(bucket: "{self.bucket}")
            |> range(start: {day_start.isoformat()}, stop: {day_end.isoformat()})
            |> filter(fn: (r) => r["_measurement"] == "feeding_cumulative")
            |> filter(fn: (r) => r["device_id"] == "{device_id}")
            |> filter(fn: (r) => r["_field"] == "feeding_total")
            |> spread()
        '''
        try:
            result = self.query_api.query(query)
            total_decrease = 0.0
            for table in result:
                for record in table.records:
                    val = record.get_value()
                    if val is not None:
                        total_decrease = abs(float(val))

            if total_decrease <= 0.0:
                return None

            return build_point(
                measurement="daily_summary",
                tags={
                    "device_id":   device_id,
                    "device_type": device_type,
                    "date":        date_str,
                    "metric_type": "feeding",
                },
                fields={
                    "start_reading":  0.0,
                    "end_reading":    0.0,
                    "consumption":    0.0,
                    "runtime_hours":  0.0,
                    "feeding_amount": total_decrease,
                    "gas_consumption": 0.0,
                },
                timestamp=day_start,
            )
        except Exception as e:
            logger.warning("[DailySummary] 计算投料量失败 (%s): %s", device_id, e)
            return None


    # ------------------------------------------------------------
    # 6. force_recalculate_range() - 强制重算指定日期范围的汇总数据
    # ------------------------------------------------------------
    def force_recalculate_range(
        self,
        start_date: str,
        end_date: str,
        polling_interval: float = None,
    ) -> Dict[str, Any]:
        """强制重算指定日期范围的日汇总数据

        1. 删除 InfluxDB 中该日期范围的 daily_summary 记录
        2. 临时覆盖 _polling_interval (如果指定, 仅影响 max_gap 断连判断)
        3. 逐天调用 calculate_and_store_daily_summary 重新计算
        4. 恢复原始 _polling_interval

        注意: 日期字符串 (YYYY-MM-DD) 解释为北京日期。
        新算法使用 elapsed() 真实时差累加, polling_interval 不再直接参与
        运行时长计算, 仅用于 max_gap = polling_interval * 12 的断连阈值判定。

        Args:
            start_date: 开始日期 (YYYY-MM-DD, 北京日期)
            end_date:   结束日期 (YYYY-MM-DD, 北京日期)
            polling_interval: 轮询间隔 (秒), 仅影响断连判定阈值, 为 None 时使用配置值
        """
        # 将日期字符串解释为北京时间 0:00
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=BEIJING_TZ)
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=BEIJING_TZ)

        if start_dt > end_dt:
            raise ValueError(f"start_date({start_date}) > end_date({end_date})")

        # 计算需要重算的天数
        total_days = (end_dt - start_dt).days + 1
        logger.info(
            "[DailySummary] 强制重算: %s ~ %s (%d天), polling_interval=%s",
            start_date, end_date, total_days,
            polling_interval if polling_interval else f"{self._polling_interval}(config)",
        )

        # 1) 删除旧记录: 范围 = [start_dt 北京0:00 UTC, end_dt+1d 北京0:00 UTC)
        delete_start = start_dt.astimezone(timezone.utc)
        delete_stop = (end_dt + timedelta(days=1)).astimezone(timezone.utc)
        predicate = '_measurement="daily_summary"'
        try:
            self.client.delete_api().delete(
                start=delete_start,
                stop=delete_stop,
                predicate=predicate,
                bucket=self.bucket,
                org=self.org,
            )
            logger.info("[DailySummary] 已删除旧记录: %s ~ %s", delete_start, delete_stop)
        except Exception as e:
            logger.error("[DailySummary] 删除旧记录失败: %s", e, exc_info=True)
            raise

        # 2) 临时覆盖 polling_interval
        original_interval = self._polling_interval
        if polling_interval is not None:
            self._polling_interval = polling_interval
            logger.info(
                "[DailySummary] 临时覆盖 polling_interval: %s -> %s",
                original_interval, polling_interval,
            )

        # 3) 逐天重算
        success_count = 0
        fail_count = 0
        try:
            current = start_dt
            while current <= end_dt:
                try:
                    self.calculate_and_store_daily_summary(current)
                    success_count += 1
                except Exception as e:
                    fail_count += 1
                    logger.error(
                        "[DailySummary] 重算 %s 失败: %s",
                        current.strftime("%Y-%m-%d"), e, exc_info=True,
                    )
                current += timedelta(days=1)
        finally:
            # 4) 恢复原始 polling_interval
            if polling_interval is not None:
                self._polling_interval = original_interval
                logger.info(
                    "[DailySummary] 恢复 polling_interval: %s", original_interval,
                )

        result = {
            "start_date": start_date,
            "end_date": end_date,
            "polling_interval_used": polling_interval if polling_interval else original_interval,
            "total_days": total_days,
            "success_count": success_count,
            "fail_count": fail_count,
        }
        logger.info("[DailySummary] 强制重算完成: %s", result)
        return result


# ============================================================
# 工厂函数 (单例)
# ============================================================
def get_daily_summary_service() -> DailySummaryService:
    """获取 DailySummaryService 单例"""
    global _instance
    if _instance is None:
        _instance = DailySummaryService()
    return _instance
