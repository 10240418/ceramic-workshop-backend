# ============================================================
# 文件说明: data_export_service.py - 数据导出统计服务
# ============================================================
# 功能:
# 1. 燃气流量统计（按天）
# 2. 投料量统计（按天）
# 3. 设备电量统计（按天，含运行时长）
# ============================================================
# 方法列表:
# 1. calculate_gas_consumption_by_day()      - 燃气消耗按天统计
# 2. calculate_feeding_amount_by_day()       - 投料量按天统计
# 3. calculate_electricity_consumption_by_day() - 电量消耗按天统计（含运行时长）
# ============================================================

from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List
import math

from config import get_settings
from app.core.influxdb import get_influx_client
from app.core.timezone_utils import to_beijing, beijing_isoformat, BEIJING_TZ

settings = get_settings()

# 🔧 单例实例
_export_service_instance: Optional['DataExportService'] = None


class DataExportService:
    """数据导出统计服务（单例模式）"""
    
    def __init__(self):
        self._client = None
        self._query_api = None
        self.bucket = settings.influx_bucket
        self.power_threshold = 0.01  # 功率阈值 (kW)
    
    @property
    def client(self):
        """延迟获取 InfluxDB 客户端"""
        if self._client is None:
            self._client = get_influx_client()
        return self._client
    
    @property
    def query_api(self):
        """延迟获取 query_api"""
        return self.client.query_api()
    
    def _format_timestamp(self, dt: datetime) -> str:
        """格式化时间戳（去掉微秒，统一格式）
        
        Args:
            dt: datetime 对象
            
        Returns:
            格式化的时间戳字符串，格式: 2026-01-26T12:00:00+00:00
        """
        # 去掉微秒
        dt_no_microsecond = dt.replace(microsecond=0)
        return dt_no_microsecond.isoformat()
    
    # ------------------------------------------------------------
    # 1. calculate_gas_consumption_by_day() - 燃气消耗按天统计
    # ------------------------------------------------------------
    def calculate_gas_consumption_by_day(
        self,
        device_ids: List[str],
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """计算燃气消耗按天统计
        
        Args:
            device_ids: 设备ID列表（如 ["scr_1", "scr_2"]）
            start_time: 开始时间（UTC）
            end_time: 结束时间（UTC）
            
        Returns:
            {
                "device_id": "scr_1",
                "total_days": 3,
                "daily_records": [
                    {
                        "day": 1,
                        "date": "2026-01-26",
                        "start_time": "2026-01-26T00:00:00Z",
                        "end_time": "2026-01-26T23:59:59Z",
                        "start_reading": 1234.56,  # m³
                        "end_reading": 1456.78,    # m³
                        "consumption": 222.22      # m³
                    },
                    ...
                ]
            }
        """
        results = {}
        
        for device_id in device_ids:
            daily_records = []
            
            # 按天分割时间段
            current_date = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
            day_count = 0
            
            while current_date < end_time:
                day_count += 1
                day_start = max(current_date, start_time)
                day_end = min(current_date + timedelta(days=1) - timedelta(seconds=1), end_time)
                
                # 查询当天的起始读数和结束读数
                start_reading = self._get_gas_reading_at_time(device_id, day_start)
                end_reading = self._get_gas_reading_at_time(device_id, day_end)
                
                # 计算消耗：
                # 🔧 修复：如果开始读数为None，使用0作为起始值
                consumption = 0.0
                if end_reading is not None:
                    start_value = start_reading if start_reading is not None else 0.0
                    consumption = round(end_reading - start_value, 2)
                    # 确保消耗量不为负数
                    if consumption < 0:
                        consumption = round(end_reading, 2)
                
                daily_records.append({
                    "day": day_count,
                    "date": current_date.strftime("%Y-%m-%d"),
                    "start_time": self._format_timestamp(day_start),
                    "end_time": self._format_timestamp(day_end),
                    "start_reading": round(start_reading, 2) if start_reading is not None else None,
                    "end_reading": round(end_reading, 2) if end_reading is not None else None,
                    "consumption": consumption
                })
                
                current_date += timedelta(days=1)
            
            results[device_id] = {
                "device_id": device_id,
                "total_days": day_count,
                "daily_records": daily_records
            }
        
        return results
    
    def _get_gas_reading_at_time(self, device_id: str, target_time: datetime) -> float:
        """获取指定时间点的燃气表读数
        
        Args:
            device_id: 设备ID（如 scr_1, scr_2）
            target_time: 目标时间
            
        Returns:
            燃气表读数（m³），如果没有数据则返回 0.0
        """
        # 🔧 查询目标时间前后1小时内的数据（扩大窗口以确保找到数据）
        window_start = target_time - timedelta(hours=1)
        window_end = target_time + timedelta(hours=1)
        
        # 🔧 SCR燃气表需要使用 gas_meter 的 module_tag
        query = f'''
        from(bucket: "{self.bucket}")
            |> range(start: {window_start.isoformat()}, stop: {window_end.isoformat()})
            |> filter(fn: (r) => r["_measurement"] == "sensor_data")
            |> filter(fn: (r) => r["device_id"] == "{device_id}")
            |> filter(fn: (r) => r["module_tag"] == "gas_meter")
            |> filter(fn: (r) => r["_field"] == "total_flow")
            |> last()
        '''
        
        try:
            result = self.query_api.query(query)
            for table in result:
                for record in table.records:
                    return record.get_value()
            
            # 🔧 如果在时间窗口内没找到数据，直接返回 0
            print(f"⚠️  未找到 {device_id} 在时间窗口内的燃气读数，使用 0 作为默认值")
            return 0.0
            
        except Exception as e:
            print(f"⚠️  查询 {device_id} 燃气读数失败: {str(e)}")
            return 0.0
    
    # ------------------------------------------------------------
    # 2. calculate_feeding_amount_by_day() - 投料量按天统计（按设备分组）
    # ------------------------------------------------------------
    def calculate_feeding_amount_by_day(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """计算投料量按天统计（按设备分组）
        
        从 feeding_records measurement 中查询投料记录，按设备和天分组
        
        Args:
            start_time: 开始时间（UTC）
            end_time: 结束时间（UTC）
            
        Returns:
            {
                "hoppers": [
                    {
                        "device_id": "short_hopper_1",
                        "daily_records": [
                            {
                                "date": "2026-01-26",
                                "start_time": "...",
                                "end_time": "...",
                                "feeding_amount": 123.45
                            },
                            ...
                        ]
                    },
                    ...
                ]
            }
        """
        # 料仓设备列表（只有7个有投料数据，no_hopper_1和no_hopper_2没有料仓）
        hopper_ids = [
            "short_hopper_1", "short_hopper_2", "short_hopper_3", "short_hopper_4",
            "long_hopper_1", "long_hopper_2", "long_hopper_3"
        ]
        
        hoppers = []
        
        for device_id in hopper_ids:
            daily_records = []
            
            # 按天分割时间段
            current_date = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
            
            while current_date < end_time:
                day_start = max(current_date, start_time)
                day_end = min(current_date + timedelta(days=1) - timedelta(seconds=1), end_time)
                
                # 查询当天该设备的投料记录
                query = f'''
                from(bucket: "{self.bucket}")
                    |> range(start: {day_start.isoformat()}, stop: {day_end.isoformat()})
                    |> filter(fn: (r) => r["_measurement"] == "feeding_records")
                    |> filter(fn: (r) => r["device_id"] == "{device_id}")
                    |> filter(fn: (r) => r["_field"] == "added_weight")
                    |> sum()
                '''
                
                feeding_amount = 0.0
                
                try:
                    result = self.query_api.query(query)
                    for table in result:
                        for record in table.records:
                            feeding_amount = record.get_value()
                            break
                
                except Exception as e:
                    print(f"⚠️  查询 {device_id} 在 {current_date.date()} 的投料记录失败: {str(e)}")
                
                daily_records.append({
                    "date": current_date.strftime("%Y-%m-%d"),
                    "start_time": self._format_timestamp(day_start),
                    "end_time": self._format_timestamp(day_end),
                    "feeding_amount": round(feeding_amount, 2)
                })
                
                current_date += timedelta(days=1)
            
            hoppers.append({
                "device_id": device_id,
                "daily_records": daily_records
            })
        
        return {
            "hoppers": hoppers
        }
    
    # ------------------------------------------------------------
    # 3. calculate_electricity_consumption_by_day() - 电量消耗按天统计
    # ------------------------------------------------------------
    def calculate_electricity_consumption_by_day(
        self,
        device_id: str,
        device_type: str,
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """计算设备电量消耗按天统计（含运行时长）
        
        Args:
            device_id: 设备ID
            device_type: 设备类型（hopper/roller_kiln/scr/fan）
            start_time: 开始时间（UTC）
            end_time: 结束时间（UTC）
            
        Returns:
            {
                "device_id": "short_hopper_1",
                "device_type": "short_hopper",
                "total_days": 3,
                "daily_records": [
                    {
                        "day": 1,
                        "date": "2026-01-26",
                        "start_time": "2026-01-26T00:00:00Z",
                        "end_time": "2026-01-26T23:59:59Z",
                        "start_reading": 1234.56,    # kWh
                        "end_reading": 1456.78,      # kWh
                        "consumption": 222.22,       # kWh
                        "runtime_hours": 18.50       # h
                    },
                    ...
                ]
            }
        """
        daily_records = []
        
        # 按天分割时间段
        current_date = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
        day_count = 0
        
        while current_date < end_time:
            day_count += 1
            day_start = max(current_date, start_time)
            day_end = min(current_date + timedelta(days=1) - timedelta(seconds=1), end_time)
            
            # 查询当天的起始读数和结束读数
            start_reading = self._get_electricity_reading_at_time(device_id, day_start)
            end_reading = self._get_electricity_reading_at_time(device_id, day_end)
            
            # 计算消耗：
            # 🔧 修复：如果开始读数为None，使用0作为起始值
            consumption = 0.0
            if end_reading is not None:
                start_value = start_reading if start_reading is not None else 0.0
                consumption = round(end_reading - start_value, 2)
                # 确保消耗量不为负数
                if consumption < 0:
                    consumption = round(end_reading, 2)
            
            # 计算运行时长
            runtime_hours = self._calculate_runtime_for_period(
                device_id, day_start, day_end
            )
            
            daily_records.append({
                "day": day_count,
                "date": current_date.strftime("%Y-%m-%d"),
                "start_time": self._format_timestamp(day_start),
                "end_time": self._format_timestamp(day_end),
                "start_reading": round(start_reading, 2) if start_reading is not None else None,
                "end_reading": round(end_reading, 2) if end_reading is not None else None,
                "consumption": consumption,
                "runtime_hours": runtime_hours
            })
            
            current_date += timedelta(days=1)
        
        return {
            "device_id": device_id,
            "device_type": device_type,
            "total_days": day_count,
            "daily_records": daily_records
        }
    
    def _get_electricity_reading_at_time(
        self, 
        device_id: str, 
        target_time: datetime,
        module_tag: Optional[str] = None
    ) -> float:
        """获取指定时间点的电表读数
        
        Args:
            device_id: 设备ID
            target_time: 目标时间
            module_tag: 模块标签（可选，用于辊道窑分区和SCR燃气表）
            
        Returns:
            电表读数（kWh），如果没有数据则返回 0.0
        """
        # 🔧 查询目标时间前后1小时内的数据（扩大窗口以确保找到数据）
        window_start = target_time - timedelta(hours=1)
        window_end = target_time + timedelta(hours=1)
        
        # 构建查询条件
        module_filter = ""
        if module_tag:
            module_filter = f'|> filter(fn: (r) => r["module_tag"] == "{module_tag}")'
        
        query = f'''
        from(bucket: "{self.bucket}")
            |> range(start: {window_start.isoformat()}, stop: {window_end.isoformat()})
            |> filter(fn: (r) => r["_measurement"] == "sensor_data")
            |> filter(fn: (r) => r["device_id"] == "{device_id}")
            {module_filter}
            |> filter(fn: (r) => r["_field"] == "ImpEp")
            |> last()
        '''
        
        try:
            result = self.query_api.query(query)
            for table in result:
                for record in table.records:
                    # ImpEp 已经是 kWh 单位，直接返回
                    value = record.get_value()
                    print(f"🔍 查询电表读数: device_id={device_id}, module_tag={module_tag}, value={value}")
                    return value
            
            # 🔧 如果在时间窗口内没找到数据，直接返回 0
            print(f"⚠️  未找到 {device_id} (module_tag={module_tag}) 在时间窗口内的电表读数，使用 0 作为默认值")
            return 0.0
            
        except Exception as e:
            print(f"⚠️  查询 {device_id} 电表读数失败: {str(e)}")
            return 0.0
    
    def _calculate_roller_zone_electricity_by_day(
        self,
        zone_id: str,
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """计算辊道窑温区电量消耗按天统计（使用 module_tag 筛选）
        
        Args:
            zone_id: 温区ID（zone1-zone6）
            start_time: 开始时间（UTC）
            end_time: 结束时间（UTC）
            
        Returns:
            {
                "device_id": "zone1",
                "device_type": "roller_kiln_zone",
                "total_days": 3,
                "daily_records": [...]
            }
        """
        daily_records = []
        
        # 按天分割时间段
        current_date = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
        day_count = 0
        
        while current_date < end_time:
            day_count += 1
            day_start = max(current_date, start_time)
            day_end = min(current_date + timedelta(days=1) - timedelta(seconds=1), end_time)
            
            # 查询当天的起始读数和结束读数（使用 module_tag）
            module_tag = f"{zone_id}_meter"
            start_reading = self._get_electricity_reading_at_time(
                "roller_kiln_1", day_start, module_tag=module_tag
            )
            end_reading = self._get_electricity_reading_at_time(
                "roller_kiln_1", day_end, module_tag=module_tag
            )
            
            # 计算消耗
            # 🔧 修复：如果开始读数为None，使用0作为起始值
            consumption = 0.0
            if end_reading is not None:
                start_value = start_reading if start_reading is not None else 0.0
                consumption = round(end_reading - start_value, 2)
                # 确保消耗量不为负数
                if consumption < 0:
                    consumption = round(end_reading, 2)
            
            # 计算运行时长
            runtime_hours = self._calculate_runtime_for_period(
                "roller_kiln_1", day_start, day_end, module_tag=module_tag
            )
            
            daily_records.append({
                "day": day_count,
                "date": current_date.strftime("%Y-%m-%d"),
                "start_time": self._format_timestamp(day_start),
                "end_time": self._format_timestamp(day_end),
                "start_reading": round(start_reading, 2) if start_reading is not None else None,
                "end_reading": round(end_reading, 2) if end_reading is not None else None,
                "consumption": consumption,
                "runtime_hours": runtime_hours
            })
            
            current_date += timedelta(days=1)
        
        return {
            "device_id": zone_id,
            "device_type": "roller_kiln_zone",
            "total_days": day_count,
            "daily_records": daily_records
        }
    
    def _calculate_runtime_for_period(
        self,
        device_id: str,
        start_time: datetime,
        end_time: datetime,
        module_tag: Optional[str] = None
    ) -> float:
        """计算指定时间段内的运行时长
        
        Args:
            device_id: 设备ID
            start_time: 开始时间
            end_time: 结束时间
            module_tag: 模块标签（可选，用于辊道窑分区和SCR燃气表）
            
        Returns:
            运行时长（小时）
        """
        # 构建查询条件
        module_filter = ""
        if module_tag:
            module_filter = f'|> filter(fn: (r) => r["module_tag"] == "{module_tag}")'
        
        query = f'''
        from(bucket: "{self.bucket}")
            |> range(start: {start_time.isoformat()}, stop: {end_time.isoformat()})
            |> filter(fn: (r) => r["_measurement"] == "sensor_data")
            |> filter(fn: (r) => r["device_id"] == "{device_id}")
            {module_filter}
            |> filter(fn: (r) => r["_field"] == "Pt")
            |> filter(fn: (r) => r["_value"] > {self.power_threshold})
            |> count()
        '''
        
        try:
            result = self.query_api.query(query)
            running_points = 0
            
            for table in result:
                for record in table.records:
                    running_points = record.get_value()
                    break
            
            # 计算运行时间（假设数据采集间隔为6秒）
            polling_interval_seconds = 6
            runtime_seconds = running_points * polling_interval_seconds
            runtime_hours = round(runtime_seconds / 3600, 2)
            
            print(f"🔍 计算运行时长: device_id={device_id}, module_tag={module_tag}, points={running_points}, hours={runtime_hours}")
            
            return runtime_hours
        except Exception as e:
            print(f"⚠️  计算 {device_id} 运行时长失败: {str(e)}")
            return 0.0
    
    def _calculate_gas_meter_runtime(
        self,
        device_id: str,
        start_time: datetime,
        end_time: datetime
    ) -> float:
        """计算SCR燃气表的运行时长（基于燃气流量）
        
        Args:
            device_id: 设备ID（scr_1 或 scr_2）
            start_time: 开始时间
            end_time: 结束时间
            
        Returns:
            运行时长（小时）
        """
        # 查询燃气流量数据，流量 > 0.01 m³/h 表示运行中
        query = f'''
        from(bucket: "{self.bucket}")
            |> range(start: {start_time.isoformat()}, stop: {end_time.isoformat()})
            |> filter(fn: (r) => r["_measurement"] == "sensor_data")
            |> filter(fn: (r) => r["device_id"] == "{device_id}")
            |> filter(fn: (r) => r["module_tag"] == "gas_meter")
            |> filter(fn: (r) => r["_field"] == "flow_rate")
            |> filter(fn: (r) => r["_value"] > 0.01)
            |> count()
        '''
        
        try:
            result = self.query_api.query(query)
            running_points = 0
            
            for table in result:
                for record in table.records:
                    running_points = record.get_value()
                    break
            
            # 计算运行时间（假设数据采集间隔为6秒）
            polling_interval_seconds = 6
            runtime_seconds = running_points * polling_interval_seconds
            runtime_hours = round(runtime_seconds / 3600, 2)
            
            print(f"🔍 计算燃气表运行时长: device_id={device_id}, points={running_points}, hours={runtime_hours}")
            
            return runtime_hours
        except Exception as e:
            print(f"⚠️  计算 {device_id} 燃气表运行时长失败: {str(e)}")
            return 0.0
    
    def _calculate_scr_pump_electricity_by_day(
        self,
        device_id: str,
        pump_id: str,
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """计算SCR氨水泵电量消耗按天统计（使用 module_tag=meter）
        
        Args:
            device_id: 设备ID（scr_1 或 scr_2）
            pump_id: 氨水泵ID（scr_1_pump 或 scr_2_pump）
            start_time: 开始时间（UTC）
            end_time: 结束时间（UTC）
            
        Returns:
            {
                "device_id": "scr_1_pump",
                "device_type": "scr_pump",
                "total_days": 3,
                "daily_records": [...]
            }
        """
        daily_records = []
        
        # 按天分割时间段
        current_date = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
        day_count = 0
        
        while current_date < end_time:
            day_count += 1
            day_start = max(current_date, start_time)
            day_end = min(current_date + timedelta(days=1) - timedelta(seconds=1), end_time)
            
            # 查询当天的起始读数和结束读数（使用 device_id=scr_1/scr_2 + module_tag=meter）
            start_reading = self._get_electricity_reading_at_time(
                device_id, day_start, module_tag="meter"
            )
            end_reading = self._get_electricity_reading_at_time(
                device_id, day_end, module_tag="meter"
            )
            
            # 计算消耗
            consumption = 0.0
            if end_reading is not None:
                start_value = start_reading if start_reading is not None else 0.0
                consumption = round(end_reading - start_value, 2)
                if consumption < 0:
                    consumption = round(end_reading, 2)
            
            # 计算运行时长（使用 device_id=scr_1/scr_2 + module_tag=meter）
            runtime_hours = self._calculate_runtime_for_period(
                device_id, day_start, day_end, module_tag="meter"
            )
            
            daily_records.append({
                "day": day_count,
                "date": current_date.strftime("%Y-%m-%d"),
                "start_time": self._format_timestamp(day_start),
                "end_time": self._format_timestamp(day_end),
                "start_reading": round(start_reading, 2) if start_reading is not None else None,
                "end_reading": round(end_reading, 2) if end_reading is not None else None,
                "consumption": consumption,
                "runtime_hours": runtime_hours
            })
            
            current_date += timedelta(days=1)
        
        return {
            "device_id": pump_id,  # 返回 scr_1_pump/scr_2_pump 作为 device_id
            "device_type": "scr_pump",
            "total_days": day_count,
            "daily_records": daily_records
        }
    
    # ------------------------------------------------------------
    # 4. calculate_all_devices_electricity_by_day() - 所有设备电量统计
    # ------------------------------------------------------------
    def calculate_all_devices_electricity_by_day(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """计算所有设备的电量消耗按天统计
        
        包括：
        - 9个回转窑（料仓）
        - 6个辊道窑分区 + 1个辊道窑合计
        - 2个SCR（氨泵电表）
        - 2个风机
        
        Args:
            start_time: 开始时间（UTC）
            end_time: 结束时间（UTC）
            
        Returns:
            {
                "start_time": "...",
                "end_time": "...",
                "hoppers": [...],
                "roller_kiln_zones": [...],  # 6个分区
                "roller_kiln_total": {...},  # 合计
                "scr_devices": [...],
                "fan_devices": [...]
            }
        """
        result = {
            "start_time": self._format_timestamp(start_time),
            "end_time": self._format_timestamp(end_time),
            "hoppers": [],
            "roller_kiln_zones": [],
            "roller_kiln_total": {},
            "scr_devices": [],
            "fan_devices": []
        }
        
        # 1. 回转窑（料仓）
        hopper_ids = [
            "short_hopper_1", "short_hopper_2", "short_hopper_3", "short_hopper_4",
            "no_hopper_1", "no_hopper_2",
            "long_hopper_1", "long_hopper_2", "long_hopper_3"
        ]
        
        for hopper_id in hopper_ids:
            data = self.calculate_electricity_consumption_by_day(
                device_id=hopper_id,
                device_type="hopper",
                start_time=start_time,
                end_time=end_time
            )
            result["hoppers"].append(data)
        
        # 2. 辊道窑6个分区
        zone_ids = ["zone1", "zone2", "zone3", "zone4", "zone5", "zone6"]
        for zone_id in zone_ids:
            zone_data = self._calculate_roller_zone_electricity_by_day(
                zone_id=zone_id,
                start_time=start_time,
                end_time=end_time
            )
            result["roller_kiln_zones"].append(zone_data)
        
        # 3. 辊道窑合计
        total_data = self.calculate_electricity_consumption_by_day(
            device_id="roller_kiln_total",
            device_type="roller_kiln_total",
            start_time=start_time,
            end_time=end_time
        )
        
        # 🔧 计算6个温区的平均运行时长（而不是使用总表的运行时长）
        zone_runtime_by_date = {}
        for zone_data in result["roller_kiln_zones"]:
            for record in zone_data["daily_records"]:
                date = record["date"]
                if date not in zone_runtime_by_date:
                    zone_runtime_by_date[date] = []
                zone_runtime_by_date[date].append(record["runtime_hours"])
        
        # 修改合计的运行时长为平均值
        for record in total_data["daily_records"]:
            date = record["date"]
            if date in zone_runtime_by_date and len(zone_runtime_by_date[date]) > 0:
                avg_runtime = round(sum(zone_runtime_by_date[date]) / len(zone_runtime_by_date[date]), 2)
                record["runtime_hours"] = avg_runtime
        
        result["roller_kiln_total"] = total_data
        
        # 4. SCR设备（氨泵）- 使用 scr_1/scr_2 + module_tag=meter
        scr_configs = [
            {"device_id": "scr_1", "pump_id": "scr_1_pump"},
            {"device_id": "scr_2", "pump_id": "scr_2_pump"}
        ]
        for config in scr_configs:
            data = self._calculate_scr_pump_electricity_by_day(
                device_id=config["device_id"],
                pump_id=config["pump_id"],
                start_time=start_time,
                end_time=end_time
            )
            result["scr_devices"].append(data)
        
        # 5. 风机
        fan_ids = ["fan_1", "fan_2"]
        for fan_id in fan_ids:
            data = self.calculate_electricity_consumption_by_day(
                device_id=fan_id,
                device_type="fan",
                start_time=start_time,
                end_time=end_time
            )
            result["fan_devices"].append(data)
        
        return result
    
    # ------------------------------------------------------------
    # 4. calculate_all_devices_runtime_by_day() - 所有设备运行时长统计
    # ------------------------------------------------------------
    def calculate_all_devices_runtime_by_day(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """计算所有设备的运行时长按天统计（专门用于运行时长导出）
        
        包括：
        - 9个回转窑（料仓）
        - 6个辊道窑分区 + 1个辊道窑合计
        - 2个SCR（氨泵）
        - 2个风机
        
        Args:
            start_time: 开始时间（UTC）
            end_time: 结束时间（UTC）
            
        Returns:
            {
                "start_time": "...",
                "end_time": "...",
                "hoppers": [
                    {
                        "device_id": "short_hopper_1",
                        "device_type": "hopper",
                        "total_days": 3,
                        "daily_records": [
                            {
                                "day": 1,
                                "date": "2026-01-26",
                                "start_time": "2026-01-26T00:00:00Z",
                                "end_time": "2026-01-26T23:59:59Z",
                                "runtime_hours": 18.50
                            },
                            ...
                        ]
                    },
                    ...
                ],
                "roller_kiln_zones": [...],  # 6个分区
                "roller_kiln_total": {...},  # 合计
                "scr_devices": [...],
                "fan_devices": [...]
            }
        """
        result = {
            "start_time": self._format_timestamp(start_time),
            "end_time": self._format_timestamp(end_time),
            "hoppers": [],
            "roller_kiln_zones": [],
            "roller_kiln_total": {},
            "scr_devices": [],
            "fan_devices": []
        }
        
        # 1. 回转窑（料仓）- 只返回运行时长
        hopper_ids = [
            "short_hopper_1", "short_hopper_2", "short_hopper_3", "short_hopper_4",
            "no_hopper_1", "no_hopper_2",
            "long_hopper_1", "long_hopper_2", "long_hopper_3"
        ]
        
        for hopper_id in hopper_ids:
            daily_records = []
            current_date = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
            day_count = 0
            
            while current_date < end_time:
                day_count += 1
                day_start = max(current_date, start_time)
                day_end = min(current_date + timedelta(days=1) - timedelta(seconds=1), end_time)
                
                # 计算运行时长
                runtime_hours = self._calculate_runtime_for_period(
                    hopper_id, day_start, day_end
                )
                
                daily_records.append({
                    "day": day_count,
                    "date": current_date.strftime("%Y-%m-%d"),
                    "start_time": self._format_timestamp(day_start),
                    "end_time": self._format_timestamp(day_end),
                    "runtime_hours": runtime_hours
                })
                
                current_date += timedelta(days=1)
            
            result["hoppers"].append({
                "device_id": hopper_id,
                "device_type": "hopper",
                "total_days": day_count,
                "daily_records": daily_records
            })
        
        # 2. 辊道窑6个分区
        zone_ids = ["zone1", "zone2", "zone3", "zone4", "zone5", "zone6"]
        for zone_id in zone_ids:
            daily_records = []
            current_date = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
            day_count = 0
            module_tag = f"{zone_id}_meter"
            
            while current_date < end_time:
                day_count += 1
                day_start = max(current_date, start_time)
                day_end = min(current_date + timedelta(days=1) - timedelta(seconds=1), end_time)
                
                # 计算运行时长（使用 module_tag）
                runtime_hours = self._calculate_runtime_for_period(
                    "roller_kiln_1", day_start, day_end, module_tag=module_tag
                )
                
                daily_records.append({
                    "day": day_count,
                    "date": current_date.strftime("%Y-%m-%d"),
                    "start_time": self._format_timestamp(day_start),
                    "end_time": self._format_timestamp(day_end),
                    "runtime_hours": runtime_hours
                })
                
                current_date += timedelta(days=1)
            
            result["roller_kiln_zones"].append({
                "device_id": zone_id,
                "device_type": "roller_kiln_zone",
                "total_days": day_count,
                "daily_records": daily_records
            })
        
        # 3. 辊道窑合计（计算6个温区的平均运行时长）
        zone_runtime_by_date = {}
        for zone_data in result["roller_kiln_zones"]:
            for record in zone_data["daily_records"]:
                date = record["date"]
                if date not in zone_runtime_by_date:
                    zone_runtime_by_date[date] = []
                zone_runtime_by_date[date].append(record["runtime_hours"])
        
        total_daily_records = []
        current_date = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
        day_count = 0
        
        while current_date < end_time:
            day_count += 1
            day_start = max(current_date, start_time)
            day_end = min(current_date + timedelta(days=1) - timedelta(seconds=1), end_time)
            date = current_date.strftime("%Y-%m-%d")
            
            # 计算平均运行时长
            avg_runtime = 0.0
            if date in zone_runtime_by_date and len(zone_runtime_by_date[date]) > 0:
                avg_runtime = round(sum(zone_runtime_by_date[date]) / len(zone_runtime_by_date[date]), 2)
            
            total_daily_records.append({
                "day": day_count,
                "date": date,
                "start_time": self._format_timestamp(day_start),
                "end_time": self._format_timestamp(day_end),
                "runtime_hours": avg_runtime
            })
            
            current_date += timedelta(days=1)
        
        result["roller_kiln_total"] = {
            "device_id": "roller_kiln_total",
            "device_type": "roller_kiln_total",
            "total_days": day_count,
            "daily_records": total_daily_records
        }
        
        # 4. SCR设备（氨泵）
        scr_ids = ["scr_1_pump", "scr_2_pump"]
        for scr_id in scr_ids:
            daily_records = []
            current_date = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
            day_count = 0
            
            while current_date < end_time:
                day_count += 1
                day_start = max(current_date, start_time)
                day_end = min(current_date + timedelta(days=1) - timedelta(seconds=1), end_time)
                
                # 计算运行时长
                runtime_hours = self._calculate_runtime_for_period(
                    scr_id, day_start, day_end
                )
                
                daily_records.append({
                    "day": day_count,
                    "date": current_date.strftime("%Y-%m-%d"),
                    "start_time": self._format_timestamp(day_start),
                    "end_time": self._format_timestamp(day_end),
                    "runtime_hours": runtime_hours
                })
                
                current_date += timedelta(days=1)
            
            result["scr_devices"].append({
                "device_id": scr_id,
                "device_type": "scr_pump",
                "total_days": day_count,
                "daily_records": daily_records
            })
        
        # 5. 风机
        fan_ids = ["fan_1", "fan_2"]
        for fan_id in fan_ids:
            daily_records = []
            current_date = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
            day_count = 0
            
            while current_date < end_time:
                day_count += 1
                day_start = max(current_date, start_time)
                day_end = min(current_date + timedelta(days=1) - timedelta(seconds=1), end_time)
                
                # 计算运行时长
                runtime_hours = self._calculate_runtime_for_period(
                    fan_id, day_start, day_end
                )
                
                daily_records.append({
                    "day": day_count,
                    "date": current_date.strftime("%Y-%m-%d"),
                    "start_time": self._format_timestamp(day_start),
                    "end_time": self._format_timestamp(day_end),
                    "runtime_hours": runtime_hours
                })
                
                current_date += timedelta(days=1)
            
            result["fan_devices"].append({
                "device_id": fan_id,
                "device_type": "fan",
                "total_days": day_count,
                "daily_records": daily_records
            })
        
        return result
    
    # ------------------------------------------------------------
    # 5. calculate_all_data_comprehensive() - 综合导出所有数据
    # ------------------------------------------------------------
    def calculate_all_data_comprehensive(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """综合导出所有设备的所有数据（按天统计）
        
        整合：电量消耗、运行时长、燃气消耗、投料量
        
        包括：
        - 9个回转窑（料仓）: 电量 + 运行时长 + 投料量
        - 1个辊道窑: 电量 + 运行时长
        - 2个SCR: 电量 + 运行时长 + 燃气消耗
        - 2个风机: 电量 + 运行时长
        
        Args:
            start_time: 开始时间（UTC）
            end_time: 结束时间（UTC）
            
        Returns:
            {
                "start_time": "...",
                "end_time": "...",
                "total_devices": 14,
                "devices": [
                    {
                        "device_id": "short_hopper_1",
                        "device_name": "窑7",
                        "device_type": "hopper",
                        "daily_records": [
                            {
                                "date": "2026-01-26",
                                "start_time": "...",
                                "end_time": "...",
                                "gas_consumption": 0.0,        # m³ (仅SCR有)
                                "feeding_amount": 123.45,      # kg (仅料仓有)
                                "electricity_consumption": 500.5,  # kWh
                                "runtime_hours": 18.5          # h
                            },
                            ...
                        ]
                    },
                    ...
                ]
            }
        """
        print(f"🔄 开始综合导出数据: {start_time} ~ {end_time}")
        
        # 1. 获取所有设备的电量和运行时长数据
        electricity_data = self.calculate_all_devices_electricity_by_day(start_time, end_time)
        
        # 2. 获取燃气消耗数据（仅SCR）
        gas_data = self.calculate_gas_consumption_by_day(
            device_ids=["scr_1", "scr_2"],
            start_time=start_time,
            end_time=end_time
        )
        
        # 3. 获取投料量数据（仅料仓）
        feeding_data = self.calculate_feeding_amount_by_day(start_time, end_time)
        
        # 4. 整合数据
        devices = []
        
        # 4.1 处理回转窑（料仓）- 有电量、运行时长、投料量
        for hopper in electricity_data["hoppers"]:
            device_id = hopper["device_id"]
            
            # 查找对应的投料量数据
            feeding_records_map = {}
            for feeding_hopper in feeding_data["hoppers"]:
                if feeding_hopper["device_id"] == device_id:
                    for record in feeding_hopper["daily_records"]:
                        feeding_records_map[record["date"]] = record["feeding_amount"]
                    break
            
            # 整合每日记录
            daily_records = []
            for elec_record in hopper["daily_records"]:
                date = elec_record["date"]
                daily_records.append({
                    "date": date,
                    "start_time": elec_record["start_time"],
                    "end_time": elec_record["end_time"],
                    "gas_consumption": 0.0,  # 料仓没有燃气消耗
                    "feeding_amount": feeding_records_map.get(date, 0.0),
                    "electricity_consumption": elec_record["consumption"],
                    "runtime_hours": elec_record["runtime_hours"]
                })
            
            devices.append({
                "device_id": device_id,
                "device_type": "hopper",
                "daily_records": daily_records
            })
        
        # 4.2 处理辊道窑 - 6个温区 + 1个合计（共7个设备）
        # 查询6个分区电表 + 1个总表（roller_kiln_total）
        zone_device_ids = ["zone1", "zone2", "zone3", "zone4", "zone5", "zone6"]
        
        for zone_id in zone_device_ids:
            # 查询每个温区的电量和运行时长（使用 module_tag 筛选）
            zone_data = self._calculate_roller_zone_electricity_by_day(
                zone_id=zone_id,
                start_time=start_time,
                end_time=end_time
            )
            
            daily_records = []
            for elec_record in zone_data["daily_records"]:
                daily_records.append({
                    "date": elec_record["date"],
                    "start_time": elec_record["start_time"],
                    "end_time": elec_record["end_time"],
                    "gas_consumption": 0.0,
                    "feeding_amount": 0.0,
                    "electricity_consumption": elec_record["consumption"],
                    "runtime_hours": elec_record["runtime_hours"]
                })
            
            devices.append({
                "device_id": zone_id,
                "device_type": "roller_kiln_zone",
                "daily_records": daily_records
            })
        
        # 查询辊道窑总表（后端已计算并存储为 roller_kiln_total）
        total_data = self.calculate_electricity_consumption_by_day(
            device_id="roller_kiln_total",
            device_type="roller_kiln_total",
            start_time=start_time,
            end_time=end_time
        )
        
        # 🔧 计算6个温区的平均运行时长（而不是总和）
        zone_runtime_by_date = {}
        for device in devices:
            if device["device_type"] == "roller_kiln_zone":
                for record in device["daily_records"]:
                    date = record["date"]
                    if date not in zone_runtime_by_date:
                        zone_runtime_by_date[date] = []
                    zone_runtime_by_date[date].append(record["runtime_hours"])
        
        daily_records = []
        for elec_record in total_data["daily_records"]:
            date = elec_record["date"]
            
            # 计算该日期6个温区的平均运行时长
            avg_runtime = 0.0
            if date in zone_runtime_by_date and len(zone_runtime_by_date[date]) > 0:
                avg_runtime = round(sum(zone_runtime_by_date[date]) / len(zone_runtime_by_date[date]), 2)
            
            daily_records.append({
                "date": date,
                "start_time": elec_record["start_time"],
                "end_time": elec_record["end_time"],
                "gas_consumption": 0.0,
                "feeding_amount": 0.0,
                "electricity_consumption": elec_record["consumption"],
                "runtime_hours": avg_runtime  # 🔧 使用平均值而不是总表的运行时长
            })
        
        devices.append({
            "device_id": "roller_kiln_total",
            "device_type": "roller_kiln_total",
            "daily_records": daily_records
        })
        
        
        # 4.3 处理SCR燃气表 - 有燃气消耗和运行时长（scr_1, scr_2）
        scr_gas_ids = ["scr_1", "scr_2"]
        for scr_id in scr_gas_ids:
            # 查找对应的燃气消耗数据
            gas_records_map = {}
            if scr_id in gas_data:
                for record in gas_data[scr_id]["daily_records"]:
                    gas_records_map[record["date"]] = record["consumption"]
            
            # 构建每日记录（有燃气消耗和运行时长）
            daily_records = []
            
            # 按天分割时间段
            current_date = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
            while current_date < end_time:
                date = current_date.strftime("%Y-%m-%d")
                day_start = max(current_date, start_time)
                day_end = min(current_date + timedelta(days=1) - timedelta(seconds=1), end_time)
                
                # 计算运行时长（基于燃气流量 > 0.01 m³/h）
                runtime_hours = self._calculate_gas_meter_runtime(
                    scr_id, day_start, day_end
                )
                
                daily_records.append({
                    "date": date,
                    "start_time": self._format_timestamp(day_start),
                    "end_time": self._format_timestamp(day_end),
                    "gas_consumption": gas_records_map.get(date, 0.0),
                    "feeding_amount": 0.0,
                    "electricity_consumption": 0.0,  # 燃气表没有电量数据
                    "runtime_hours": runtime_hours  # 根据燃气流量计算运行时长
                })
                
                current_date += timedelta(days=1)
            
            devices.append({
                "device_id": scr_id,
                "device_type": "scr_gas_meter",
                "daily_records": daily_records
            })
        
        # 4.4 处理SCR氨水泵 - 使用 scr_1/scr_2 + module_tag=meter
        scr_pump_configs = [
            {"device_id": "scr_1", "pump_id": "scr_1_pump"},
            {"device_id": "scr_2", "pump_id": "scr_2_pump"}
        ]
        for config in scr_pump_configs:
            pump_data = self._calculate_scr_pump_electricity_by_day(
                device_id=config["device_id"],
                pump_id=config["pump_id"],
                start_time=start_time,
                end_time=end_time
            )
            
            daily_records = []
            for elec_record in pump_data["daily_records"]:
                daily_records.append({
                    "date": elec_record["date"],
                    "start_time": elec_record["start_time"],
                    "end_time": elec_record["end_time"],
                    "gas_consumption": 0.0,
                    "feeding_amount": 0.0,
                    "electricity_consumption": elec_record["consumption"],
                    "runtime_hours": elec_record["runtime_hours"]
                })
            
            devices.append({
                "device_id": config["pump_id"],
                "device_type": "scr_pump",
                "daily_records": daily_records
            })
        
        # 4.5 处理风机 - 有电量、运行时长
        for fan in electricity_data["fan_devices"]:
            daily_records = []
            for elec_record in fan["daily_records"]:
                daily_records.append({
                    "date": elec_record["date"],
                    "start_time": elec_record["start_time"],
                    "end_time": elec_record["end_time"],
                    "gas_consumption": 0.0,  # 风机没有燃气消耗
                    "feeding_amount": 0.0,   # 风机没有投料
                    "electricity_consumption": elec_record["consumption"],
                    "runtime_hours": elec_record["runtime_hours"]
                })
            
            devices.append({
                "device_id": fan["device_id"],
                "device_type": "fan",
                "daily_records": daily_records
            })
        
        print(f"✅ 综合导出完成: {len(devices)} 个设备")
        
        return {
            "start_time": self._format_timestamp(start_time),
            "end_time": self._format_timestamp(end_time),
            "total_devices": len(devices),
            "devices": devices
        }


# ------------------------------------------------------------
# 单例获取函数
# ------------------------------------------------------------
def get_export_service() -> DataExportService:
    """获取数据导出服务单例"""
    global _export_service_instance
    if _export_service_instance is None:
        _export_service_instance = DataExportService()
    return _export_service_instance

