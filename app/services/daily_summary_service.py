# ============================================================
# 文件说明: daily_summary_service.py - 日汇总数据计算与存储服务
# ============================================================
# 方法列表:
# 1. calculate_and_store_daily_summary() - 计算并存储指定日期的汇总数据
# 2. check_and_fill_missing_dates()      - 检测并补全缺失的日期数据
# 3. get_available_dates()               - 获取已有的日期列表
# 4. get_daily_summary()                 - 查询日汇总数据
# ============================================================

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from influxdb_client import Point

from app.core.influxdb import build_point, get_influx_client, write_points_batch
from config import get_settings

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

# 辊道窑温区列表 (zone1~zone6, 在 module_data 中对应 sensor_type=zone1_meter 等)
ROLLER_KILN_ZONES = [
    {"device_id": "zone1", "device_type": "roller_kiln_zone", "sensor_type": "zone1_meter"},
    {"device_id": "zone2", "device_type": "roller_kiln_zone", "sensor_type": "zone2_meter"},
    {"device_id": "zone3", "device_type": "roller_kiln_zone", "sensor_type": "zone3_meter"},
    {"device_id": "zone4", "device_type": "roller_kiln_zone", "sensor_type": "zone4_meter"},
    {"device_id": "zone5", "device_type": "roller_kiln_zone", "sensor_type": "zone5_meter"},
    {"device_id": "zone6", "device_type": "roller_kiln_zone", "sensor_type": "zone6_meter"},
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

# 最小运行功率阈值 (kW)，低于此值认为设备未运行
RUNTIME_POWER_THRESHOLD = 1.0


class DailySummaryService:
    """日汇总数据计算与存储服务（单例模式）"""

    def __init__(self):
        self._client = None
        self._query_api = None
        self.bucket = settings.influx_bucket
        self.org = settings.influx_org

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

        Args:
            target_dt: 目标日期 (UTC)

        Returns:
            {
                "date": "2026-01-26",
                "success": True,
                "devices_processed": 20,
                "points_written": 80
            }
        """
        date_str = target_dt.strftime("%Y%m%d")
        date_label = target_dt.strftime("%Y-%m-%d")

        # 当天开始/结束时间 (UTC)
        day_start = target_dt.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)

        print(f"[INFO] 开始计算日汇总: {date_label}")

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

        # 2. 计算辊道窑温区电量
        for zone in ROLLER_KILN_ZONES:
            device_id = zone["device_id"]
            device_type = zone["device_type"]
            sensor_type = zone["sensor_type"]

            elec_point = self._calc_roller_kiln_electricity_point(
                device_id, device_type, date_str, day_start, day_end, sensor_type
            )
            if elec_point:
                all_points.append(elec_point)

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

        # 5. 批量写入
        points_written = 0
        if all_points:
            success, err = write_points_batch(all_points)
            if success:
                points_written = len(all_points)
                print(f"[OK] 日汇总写入完成: {date_label}, {points_written} 个数据点")
            else:
                print(f"[ERROR] 日汇总写入失败: {date_label}, {err}")
                return {
                    "date": date_label,
                    "success": False,
                    "error": err,
                    "devices_processed": devices_processed,
                    "points_written": 0,
                }
        else:
            print(f"[WARN] 日汇总: {date_label} 无有效数据点")

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

        if not existing_dates:
            # 没有任何数据，从 30 天前开始
            start_dt = end_dt - timedelta(days=30)
        else:
            first_date_str = existing_dates[0]  # YYYYMMDD
            start_dt = datetime.strptime(first_date_str, "%Y%m%d").replace(tzinfo=timezone.utc)

        # 生成期望的日期列表
        expected_dates = []
        cur = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        end = end_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        while cur <= end:
            expected_dates.append(cur.strftime("%Y%m%d"))
            cur += timedelta(days=1)

        existing_set = set(existing_dates)
        missing_dates = [d for d in expected_dates if d not in existing_set]

        print(f"[INFO] 检测缺失日期: 共 {len(expected_dates)} 天, 缺失 {len(missing_dates)} 天")

        filled_dates = []
        for date_str in missing_dates:
            target_dt = datetime.strptime(date_str, "%Y%m%d").replace(tzinfo=timezone.utc)
            result = self.calculate_and_store_daily_summary(target_dt)
            if result.get("success") and result.get("points_written", 0) > 0:
                filled_dates.append(date_str)

        return {
            "checked_range": f"{start_dt.strftime('%Y-%m-%d')} ~ {end_dt.strftime('%Y-%m-%d')}",
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
            print(f"[ERROR] 获取可用日期失败: {e}")
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
            start_date:  开始日期 (UTC)
            end_date:    结束日期 (UTC)

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
            print(f"[ERROR] 查询日汇总失败: {e}")
            return []

    # ============================================================
    # 内部辅助方法
    # ============================================================

    def _query_first_last_value(
        self,
        field: str,
        device_id: str,
        device_type: str,
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
            |> filter(fn: (r) => r["_measurement"] == "module_data")
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
            print(f"[WARN] 查询首值失败 ({device_id}/{field}): {e}")

        try:
            result = self.query_api.query(last_q)
            for table in result:
                for record in table.records:
                    last_val = record.get_value()
                    break
                if last_val is not None:
                    break
        except Exception as e:
            print(f"[WARN] 查询尾值失败 ({device_id}/{field}): {e}")

        return (first_val, last_val)

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
            device_type=src_device_type,
            day_start=day_start,
            day_end=day_end,
        )

        if first_val is None or last_val is None:
            return None

        # 处理仪表重置 (end < start)
        consumption = max(0.0, float(last_val) - float(first_val))

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
                "runtime_hours": 0.0,
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
        sensor_type: str,
    ) -> Optional[Point]:
        """计算辊道窑温区电量 Point"""
        extra_filter = f'|> filter(fn: (r) => r["sensor_type"] == "{sensor_type}")'
        first_val, last_val = self._query_first_last_value(
            field="ImpEp",
            device_id="roller_kiln_1",
            device_type="roller_kiln",
            day_start=day_start,
            day_end=day_end,
            extra_filter=extra_filter,
        )

        if first_val is None or last_val is None:
            return None

        consumption = max(0.0, float(last_val) - float(first_val))

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
                "runtime_hours":  0.0,
                "feeding_amount": 0.0,
                "gas_consumption": 0.0,
            },
            timestamp=day_start,
        )

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
            device_type=device_type,
            day_start=day_start,
            day_end=day_end,
        )

        if first_val is None or last_val is None:
            return None

        gas_consumption = max(0.0, float(last_val) - float(first_val))

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
                "runtime_hours":   0.0,
                "feeding_amount":  0.0,
                "gas_consumption": gas_consumption,
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
        """计算投料量 Point (统计当天重量净减少量)"""
        query = f'''
        from(bucket: "{self.bucket}")
            |> range(start: {day_start.isoformat()}, stop: {day_end.isoformat()})
            |> filter(fn: (r) => r["_measurement"] == "module_data")
            |> filter(fn: (r) => r["device_id"] == "{device_id}")
            |> filter(fn: (r) => r["_field"] == "weight")
            |> derivative(unit: 1s, nonNegative: false)
            |> filter(fn: (r) => r["_value"] < 0.0)
            |> sum()
        '''
        try:
            result = self.query_api.query(query)
            total_decrease = 0.0
            for table in result:
                for record in table.records:
                    val = record.get_value()
                    if val is not None:
                        total_decrease += abs(float(val))

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
            print(f"[WARN] 计算投料量失败 ({device_id}): {e}")
            return None


# ============================================================
# 工厂函数 (单例)
# ============================================================
def get_daily_summary_service() -> DailySummaryService:
    """获取 DailySummaryService 单例"""
    global _instance
    if _instance is None:
        _instance = DailySummaryService()
    return _instance
