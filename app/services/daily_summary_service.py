# ============================================================
# 文件说明: daily_summary_service.py - 日汇总数据服务
# ============================================================
# 功能:
# 1. 计算并存储每日汇总数据（电量、燃气、投料、运行时长）
# 2. 自动检测并补全缺失的日期数据
# 3. 查询已有的日汇总数据
# ============================================================
# 方法列表:
# 1. calculate_and_store_daily_summary()     - 计算并存储指定日期的汇总数据
# 2. check_and_fill_missing_dates()          - 检测并补全缺失日期
# 3. get_daily_summary()                     - 查询日汇总数据
# 4. get_available_dates()                   - 获取已有的日期列表
# ============================================================

from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List
from influxdb_client import Point

from config import get_settings
from app.core.influxdb import get_influx_client
from app.services.data_export_service import get_export_service

settings = get_settings()

# 🔧 单例实例
_daily_summary_service_instance: Optional['DailySummaryService'] = None


class DailySummaryService:
    """日汇总数据服务（单例模式）"""
    
    def __init__(self):
        self._client = None
        self._write_api = None
        self._query_api = None
        self.bucket = settings.influx_bucket
        self.export_service = get_export_service()
    
    @property
    def client(self):
        """延迟获取 InfluxDB 客户端"""
        if self._client is None:
            self._client = get_influx_client()
        return self._client
    
    @property
    def write_api(self):
        """延迟获取 write_api"""
        if self._write_api is None:
            self._write_api = self.client.write_api()
        return self._write_api
    
    @property
    def query_api(self):
        """延迟获取 query_api"""
        if self._query_api is None:
            self._query_api = self.client.query_api()
        return self._query_api
    
    # ------------------------------------------------------------
    # 1. calculate_and_store_daily_summary() - 计算并存储日汇总
    # ------------------------------------------------------------
    def calculate_and_store_daily_summary(self, target_date: datetime) -> Dict[str, Any]:
        """计算并存储指定日期的汇总数据
        
        Args:
            target_date: 目标日期（UTC，会自动转换为当天0点）
            
        Returns:
            {
                "date": "2026-01-26",
                "success": true,
                "devices_processed": 20,
                "points_written": 80
            }
        """
        # 转换为当天0点
        date_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        date_end = date_start + timedelta(days=1) - timedelta(seconds=1)
        date_str = date_start.strftime("%Y%m%d")
        
        print(f"🔄 开始计算日汇总: {date_str} ({date_start} ~ {date_end})")
        
        points = []
        devices_processed = 0
        
        # 1. 计算所有设备的电量消耗和运行时长
        electricity_data = self.export_service.calculate_all_devices_electricity_by_day(
            start_time=date_start,
            end_time=date_end
        )
        
        # 1.1 处理回转窑（料仓）
        for hopper in electricity_data["hoppers"]:
            device_id = hopper["device_id"]
            if hopper["daily_records"]:
                record = hopper["daily_records"][0]
                
                # 电量数据点
                point = Point("daily_summary") \
                    .tag("device_id", device_id) \
                    .tag("device_type", "hopper") \
                    .tag("date", date_str) \
                    .tag("metric_type", "electricity") \
                    .field("start_reading", record.get("start_reading") or 0.0) \
                    .field("end_reading", record.get("end_reading") or 0.0) \
                    .field("consumption", record.get("consumption", 0.0)) \
                    .field("runtime_hours", record.get("runtime_hours", 0.0)) \
                    .time(date_start)
                points.append(point)
                devices_processed += 1
        
        # 1.2 处理辊道窑6个分区
        for zone in electricity_data["roller_kiln_zones"]:
            device_id = zone["device_id"]
            if zone["daily_records"]:
                record = zone["daily_records"][0]
                
                point = Point("daily_summary") \
                    .tag("device_id", device_id) \
                    .tag("device_type", "roller_kiln_zone") \
                    .tag("date", date_str) \
                    .tag("metric_type", "electricity") \
                    .field("start_reading", record.get("start_reading") or 0.0) \
                    .field("end_reading", record.get("end_reading") or 0.0) \
                    .field("consumption", record.get("consumption", 0.0)) \
                    .field("runtime_hours", record.get("runtime_hours", 0.0)) \
                    .time(date_start)
                points.append(point)
                devices_processed += 1
        
        # 1.3 处理辊道窑合计
        total = electricity_data["roller_kiln_total"]
        if total["daily_records"]:
            record = total["daily_records"][0]
            
            point = Point("daily_summary") \
                .tag("device_id", "roller_kiln_total") \
                .tag("device_type", "roller_kiln_total") \
                .tag("date", date_str) \
                .tag("metric_type", "electricity") \
                .field("start_reading", record.get("start_reading") or 0.0) \
                .field("end_reading", record.get("end_reading") or 0.0) \
                .field("consumption", record.get("consumption", 0.0)) \
                .field("runtime_hours", record.get("runtime_hours", 0.0)) \
                .time(date_start)
            points.append(point)
            devices_processed += 1
        
        # 1.4 处理SCR氨水泵
        for scr in electricity_data["scr_devices"]:
            device_id = scr["device_id"]
            if scr["daily_records"]:
                record = scr["daily_records"][0]
                
                point = Point("daily_summary") \
                    .tag("device_id", device_id) \
                    .tag("device_type", "scr_pump") \
                    .tag("date", date_str) \
                    .tag("metric_type", "electricity") \
                    .field("start_reading", record.get("start_reading") or 0.0) \
                    .field("end_reading", record.get("end_reading") or 0.0) \
                    .field("consumption", record.get("consumption", 0.0)) \
                    .field("runtime_hours", record.get("runtime_hours", 0.0)) \
                    .time(date_start)
                points.append(point)
                devices_processed += 1
        
        # 1.5 处理风机
        for fan in electricity_data["fan_devices"]:
            device_id = fan["device_id"]
            if fan["daily_records"]:
                record = fan["daily_records"][0]
                
                point = Point("daily_summary") \
                    .tag("device_id", device_id) \
                    .tag("device_type", "fan") \
                    .tag("date", date_str) \
                    .tag("metric_type", "electricity") \
                    .field("start_reading", record.get("start_reading") or 0.0) \
                    .field("end_reading", record.get("end_reading") or 0.0) \
                    .field("consumption", record.get("consumption", 0.0)) \
                    .field("runtime_hours", record.get("runtime_hours", 0.0)) \
                    .time(date_start)
                points.append(point)
                devices_processed += 1
        
        # 2. 计算燃气消耗（仅SCR）
        gas_data = self.export_service.calculate_gas_consumption_by_day(
            device_ids=["scr_1", "scr_2"],
            start_time=date_start,
            end_time=date_end
        )
        
        for device_id, data in gas_data.items():
            if data["daily_records"]:
                record = data["daily_records"][0]
                
                # 计算燃气表运行时长
                runtime_hours = self.export_service._calculate_gas_meter_runtime(
                    device_id, date_start, date_end
                )
                
                point = Point("daily_summary") \
                    .tag("device_id", device_id) \
                    .tag("device_type", "scr_gas_meter") \
                    .tag("date", date_str) \
                    .tag("metric_type", "gas") \
                    .field("start_reading", record.get("start_reading") or 0.0) \
                    .field("end_reading", record.get("end_reading") or 0.0) \
                    .field("gas_consumption", record.get("consumption", 0.0)) \
                    .field("runtime_hours", runtime_hours) \
                    .time(date_start)
                points.append(point)
                devices_processed += 1
        
        # 3. 计算投料量（仅料仓）
        feeding_data = self.export_service.calculate_feeding_amount_by_day(
            start_time=date_start,
            end_time=date_end
        )
        
        for hopper in feeding_data["hoppers"]:
            device_id = hopper["device_id"]
            if hopper["daily_records"]:
                record = hopper["daily_records"][0]
                
                point = Point("daily_summary") \
                    .tag("device_id", device_id) \
                    .tag("device_type", "hopper") \
                    .tag("date", date_str) \
                    .tag("metric_type", "feeding") \
                    .field("feeding_amount", record.get("feeding_amount", 0.0)) \
                    .time(date_start)
                points.append(point)
        
        # 4. 批量写入 InfluxDB
        if points:
            try:
                self.write_api.write(bucket=self.bucket, record=points)
                print(f"✅ 日汇总数据写入成功: {date_str}, {len(points)} 个数据点")
            except Exception as e:
                print(f"❌ 日汇总数据写入失败: {str(e)}")
                raise
        
        return {
            "date": date_start.strftime("%Y-%m-%d"),
            "success": True,
            "devices_processed": devices_processed,
            "points_written": len(points)
        }
    
    # ------------------------------------------------------------
    # 2. check_and_fill_missing_dates() - 检测并补全缺失日期
    # ------------------------------------------------------------
    def check_and_fill_missing_dates(self, end_date: Optional[datetime] = None) -> Dict[str, Any]:
        """检测并补全缺失的日期数据
        
        Args:
            end_date: 结束日期（默认为昨天，因为今天的数据还不完整）
            
        Returns:
            {
                "checked_range": "2026-01-01 ~ 2026-01-26",
                "existing_dates": ["20260102", "20260103", ...],
                "missing_dates": ["20260106"],
                "filled_dates": ["20260106"],
                "total_filled": 1
            }
        """
        if end_date is None:
            # 默认检查到昨天（今天的数据还不完整）
            end_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
        
        # 1. 获取已有的日期列表
        existing_dates = self.get_available_dates()
        existing_dates_set = set(existing_dates)
        
        # 2. 确定检查范围（从最早的数据日期到 end_date）
        if existing_dates:
            # 解析最早日期
            earliest_date_str = min(existing_dates)
            start_date = datetime.strptime(earliest_date_str, "%Y%m%d").replace(tzinfo=timezone.utc)
        else:
            # 如果没有任何数据，从30天前开始
            start_date = end_date - timedelta(days=30)
        
        print(f"🔍 检查日期范围: {start_date.date()} ~ {end_date.date()}")
        
        # 3. 找出缺失的日期
        missing_dates = []
        current_date = start_date
        
        while current_date <= end_date:
            date_str = current_date.strftime("%Y%m%d")
            if date_str not in existing_dates_set:
                missing_dates.append(date_str)
            current_date += timedelta(days=1)
        
        print(f"📊 已有日期: {len(existing_dates)} 个")
        print(f"⚠️  缺失日期: {len(missing_dates)} 个: {missing_dates}")
        
        # 4. 补全缺失的日期
        filled_dates = []
        for date_str in missing_dates:
            try:
                target_date = datetime.strptime(date_str, "%Y%m%d").replace(tzinfo=timezone.utc)
                result = self.calculate_and_store_daily_summary(target_date)
                if result["success"]:
                    filled_dates.append(date_str)
                    print(f"✅ 补全日期: {date_str}")
            except Exception as e:
                print(f"❌ 补全日期失败 {date_str}: {str(e)}")
        
        return {
            "checked_range": f"{start_date.date()} ~ {end_date.date()}",
            "existing_dates": existing_dates,
            "missing_dates": missing_dates,
            "filled_dates": filled_dates,
            "total_filled": len(filled_dates)
        }
    
    # ------------------------------------------------------------
    # 3. get_daily_summary() - 查询日汇总数据
    # ------------------------------------------------------------
    def get_daily_summary(
        self,
        device_id: str,
        metric_type: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """查询日汇总数据
        
        Args:
            device_id: 设备ID
            metric_type: 指标类型 (electricity, gas, feeding, runtime)
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            [
                {
                    "date": "20260126",
                    "start_reading": 1234.56,
                    "end_reading": 1456.78,
                    "consumption": 222.22,
                    "runtime_hours": 18.5,
                    ...
                },
                ...
            ]
        """
        query = f'''
        from(bucket: "{self.bucket}")
            |> range(start: {start_date.isoformat()}, stop: {end_date.isoformat()})
            |> filter(fn: (r) => r["_measurement"] == "daily_summary")
            |> filter(fn: (r) => r["device_id"] == "{device_id}")
            |> filter(fn: (r) => r["metric_type"] == "{metric_type}")
            |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        '''
        
        try:
            result = self.query_api.query(query)
            records = []
            
            for table in result:
                for record in table.records:
                    records.append({
                        "date": record.values.get("date"),
                        "start_reading": record.values.get("start_reading", 0.0),
                        "end_reading": record.values.get("end_reading", 0.0),
                        "consumption": record.values.get("consumption", 0.0),
                        "runtime_hours": record.values.get("runtime_hours", 0.0),
                        "feeding_amount": record.values.get("feeding_amount", 0.0),
                        "gas_consumption": record.values.get("gas_consumption", 0.0),
                    })
            
            return records
        
        except Exception as e:
            print(f"⚠️  查询日汇总数据失败: {str(e)}")
            return []
    
    # ------------------------------------------------------------
    # 4. get_available_dates() - 获取已有的日期列表
    # ------------------------------------------------------------
    def get_available_dates(self) -> List[str]:
        """获取已有的日期列表
        
        Returns:
            ["20260102", "20260103", "20260104", ...]
        """
        query = f'''
        from(bucket: "{self.bucket}")
            |> range(start: -365d)
            |> filter(fn: (r) => r["_measurement"] == "daily_summary")
            |> keep(columns: ["date"])
            |> distinct(column: "date")
        '''
        
        try:
            result = self.query_api.query(query)
            dates = set()
            
            for table in result:
                for record in table.records:
                    date = record.values.get("date")
                    if date:
                        dates.add(date)
            
            return sorted(list(dates))
        
        except Exception as e:
            print(f"⚠️  查询已有日期失败: {str(e)}")
            return []


# ------------------------------------------------------------
# 单例获取函数
# ------------------------------------------------------------
def get_daily_summary_service() -> DailySummaryService:
    """获取日汇总数据服务单例"""
    global _daily_summary_service_instance
    if _daily_summary_service_instance is None:
        _daily_summary_service_instance = DailySummaryService()
    return _daily_summary_service_instance

