# ============================================================
# 文件说明: data_export_service.py - 数据导出统计服务
# ============================================================
# 功能:
# 1. 燃气用量（按天）
# 2. 累计投料量（按天）
# 3. 设备电量统计（按天，含运行时长）
# ============================================================
# 方法列表:
# 1. calculate_gas_consumption_by_day()      - 燃气消耗按天统计
# 2. calculate_feeding_amount_by_day()       - 投料量按天统计
# 3. calculate_electricity_consumption_by_day() - 电量消耗按天统计（含运行时长）
# ============================================================

from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import math

from config import get_settings
from app.core.influxdb import get_influx_client
from app.tools.timezone_tools import to_beijing, beijing_isoformat, BEIJING_TZ
from app.tools.time_slice_tools import split_time_range_by_natural_days

settings = get_settings()

# 单例实例
_export_service_instance: Optional['DataExportService'] = None

# 内存缓存 (完整天数据)
_memory_cache: Dict[str, Any] = {}


def format_datetime_without_microseconds(dt: datetime) -> Optional[str]:
    """格式化时间, 去除微秒, 转换为北京时间"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt_beijing = dt.astimezone(BEIJING_TZ)
    dt_no_micro = dt_beijing.replace(microsecond=0)
    return dt_no_micro.isoformat()


class DataExportService:
    """数据导出统计服务（单例模式）"""
    
    def __init__(self):
        self._client = None
        self._query_api = None
        # [CRITICAL] 使用环境变量配置的 bucket
        self.bucket = settings.influx_bucket
        self.org = settings.influx_org
        self.power_threshold = 0.01  # 功率阈值 (kW)
    
    @property
    def client(self):
        """延迟获取 InfluxDB 客户端"""
        if self._client is None:
            self._client = get_influx_client()
        return self._client
    
    @property
    def query_api(self):
        """延迟获取 query_api (缓存)"""
        if self._query_api is None:
            self._query_api = self.client.query_api()
        return self._query_api
    
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
                # [FIX] 修复：如果开始读数为None，使用0作为起始值
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
        # [FIX] 查询目标时间前后1小时内的数据（扩大窗口以确保找到数据）
        window_start = target_time - timedelta(hours=1)
        window_end = target_time + timedelta(hours=1)
        
        # [FIX] SCR燃气表需要使用 gas_meter 的 module_tag
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
            
            # [FIX] 如果在时间窗口内没找到数据，直接返回 0
            print(f"[WARN]  未找到 {device_id} 在时间窗口内的燃气读数，使用 0 作为默认值")
            return 0.0
            
        except Exception as e:
            print(f"[WARN]  查询 {device_id} 燃气读数失败: {str(e)}")
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
                    print(f"[WARN]  查询 {device_id} 在 {current_date.date()} 的投料记录失败: {str(e)}")
                
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
            # [FIX] 修复：如果开始读数为None，使用0作为起始值
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
        # [FIX] 查询目标时间前后1小时内的数据（扩大窗口以确保找到数据）
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
                    print(f" 查询电表读数: device_id={device_id}, module_tag={module_tag}, value={value}")
                    return value
            
            # [FIX] 如果在时间窗口内没找到数据，直接返回 0
            print(f"[WARN]  未找到 {device_id} (module_tag={module_tag}) 在时间窗口内的电表读数，使用 0 作为默认值")
            return 0.0
            
        except Exception as e:
            print(f"[WARN]  查询 {device_id} 电表读数失败: {str(e)}")
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
            # [FIX] 修复：如果开始读数为None，使用0作为起始值
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
            
            print(f" 计算运行时长: device_id={device_id}, module_tag={module_tag}, points={running_points}, hours={runtime_hours}")
            
            return runtime_hours
        except Exception as e:
            print(f"[WARN]  计算 {device_id} 运行时长失败: {str(e)}")
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
            
            print(f" 计算燃气表运行时长: device_id={device_id}, points={running_points}, hours={runtime_hours}")
            
            return runtime_hours
        except Exception as e:
            print(f"[WARN]  计算 {device_id} 燃气表运行时长失败: {str(e)}")
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
        
        # [FIX] 计算6个温区的平均运行时长（而不是使用总表的运行时长）
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
    # 4. calculate_all_devices_runtime_by_day() - 所有设备设备运行时长
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
        print(f"[...] 开始综合导出数据: {start_time} ~ {end_time}")
        
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
        
        # [FIX] 计算6个温区的平均运行时长（而不是总和）
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
                "runtime_hours": avg_runtime  # [FIX] 使用平均值而不是总表的运行时长
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
        
        print(f"[OK] 综合导出完成: {len(devices)} 个设备")
        
        return {
            "start_time": self._format_timestamp(start_time),
            "end_time": self._format_timestamp(end_time),
            "total_devices": len(devices),
            "devices": devices
        }

    # ============================================================
    # V3 优化方法 (合并自 data_export_service_v3.py)
    # ============================================================

    # ------------------------------------------------------------
    # 延迟导入 daily_summary_service (避免循环导入)
    # ------------------------------------------------------------
    def _get_summary_service(self):
        """延迟获取 daily_summary_service 实例"""
        from app.services.daily_summary_service import get_daily_summary_service
        return get_daily_summary_service()

    # ------------------------------------------------------------
    # 核心优化 1: 批量查询预计算数据（一次查询所有设备）
    # ------------------------------------------------------------
    def _batch_query_daily_summary(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
        """批量查询所有设备的预计算数据
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            {
                "short_hopper_1": {
                    "electricity": [...],
                    "feeding": [...]
                },
                "zone1": {
                    "electricity": [...]
                },
                ...
            }
        """
        print(f"[...] 批量查询预计算数据: {start_date.date()} ~ {end_date.date()}")
        
        # [FIX] 一次性查询所有设备、所有指标类型的数据
        query = f'''
        from(bucket: "{self.bucket}")
            |> range(start: {start_date.isoformat()}, stop: {end_date.isoformat()})
            |> filter(fn: (r) => r["_measurement"] == "daily_summary")
            |> pivot(rowKey:["_time", "device_id", "metric_type", "date"], columnKey: ["_field"], valueColumn: "_value")
        '''
        
        try:
            result = self.query_api.query(query)
            
            # 按设备ID和指标类型分组
            data_by_device: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
            
            for table in result:
                for record in table.records:
                    device_id = record.values.get("device_id")
                    metric_type = record.values.get("metric_type")
                    date = record.values.get("date")
                    
                    # [FIX] 兼容性处理：daily_summary 中已经做了映射
                    # zone1~zone6 和 scr_1_pump, scr_2_pump 可以直接使用
                    
                    if device_id not in data_by_device:
                        data_by_device[device_id] = {}
                    
                    if metric_type not in data_by_device[device_id]:
                        data_by_device[device_id][metric_type] = []
                    
                    data_by_device[device_id][metric_type].append({
                        "date": date,
                        "start_reading": record.values.get("start_reading", 0.0),
                        "end_reading": record.values.get("end_reading", 0.0),
                        "consumption": record.values.get("consumption", 0.0),
                        "runtime_hours": record.values.get("runtime_hours", 0.0),
                        "feeding_amount": record.values.get("feeding_amount", 0.0),
                        "gas_consumption": record.values.get("gas_consumption", 0.0),
                    })
            
            print(f"[OK] 批量查询完成: {len(data_by_device)} 个设备")
            return data_by_device
        
        except Exception as e:
            print(f"[ERROR] 批量查询失败: {str(e)}")
            return {}
    
    # ------------------------------------------------------------
    # 核心优化 2: 并行计算不完整天（使用线程池）
    # ------------------------------------------------------------
    def _parallel_calculate_partial_days(
        self,
        device_configs: List[Dict[str, str]],
        partial_day_slices: List[Any]
    ) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
        """并行计算所有设备的不完整天数据
        
        Args:
            device_configs: 设备配置列表 [{"device_id": "xxx", "device_type": "xxx", "metric_types": ["electricity", "feeding"]}, ...]
            partial_day_slices: 不完整天的时间切片列表
            
        Returns:
            {
                "short_hopper_1": {
                    "electricity": [...],
                    "feeding": [...]
                },
                ...
            }
        """
        if not partial_day_slices:
            return {}
        
        print(f"[...] 并行计算不完整天: {len(device_configs)} 个设备 × {len(partial_day_slices)} 个时间段")
        
        data_by_device: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        
        # 使用线程池并行计算
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            
            for device_config in device_configs:
                device_id = device_config["device_id"]
                device_type = device_config["device_type"]
                metric_types = device_config["metric_types"]
                
                for metric_type in metric_types:
                    for slice_obj in partial_day_slices:
                        future = executor.submit(
                            self._calculate_realtime_single,
                            device_id,
                            device_type,
                            metric_type,
                            slice_obj
                        )
                        futures.append((future, device_id, metric_type))
            
            # 收集结果
            for future, device_id, metric_type in futures:
                try:
                    record = future.result(timeout=10)
                    
                    if device_id not in data_by_device:
                        data_by_device[device_id] = {}
                    
                    if metric_type not in data_by_device[device_id]:
                        data_by_device[device_id][metric_type] = []
                    
                    data_by_device[device_id][metric_type].append(record)
                
                except Exception as e:
                    print(f"[WARN]  计算失败 {device_id}/{metric_type}: {str(e)}")
        
        print(f"[OK] 并行计算完成: {len(data_by_device)} 个设备")
        return data_by_device
    
    def _calculate_realtime_single(
        self,
        device_id: str,
        device_type: str,
        metric_type: str,
        slice_obj: Any
    ) -> Dict[str, Any]:
        """计算单个设备、单个指标、单个时间段的实时数据
        
        [FIX] 兼容性处理：
        - 辊道窑分区 (zone1~zone6): 查询 roller_kiln_1 + module_tag 过滤
        - SCR 氨水泵 (scr_1_pump, scr_2_pump): 查询 scr_1/scr_2 + module_tag=meter
        """
        start_time = slice_obj.start_time
        end_time = slice_obj.end_time
        
        # [FIX] 映射虚拟设备ID到实际数据库存储的ID
        actual_device_id, module_tag_filter = self._map_virtual_device_to_actual(device_id, device_type)
        
        if metric_type == "electricity":
            start_reading = self._get_electricity_reading_at_time_with_filter(
                actual_device_id, module_tag_filter, start_time
            )
            end_reading = self._get_electricity_reading_at_time_with_filter(
                actual_device_id, module_tag_filter, end_time
            )
            consumption = 0.0
            if end_reading is not None:
                start_value = start_reading if start_reading is not None else 0.0
                consumption = round(end_reading - start_value, 2)
                if consumption < 0:
                    consumption = round(end_reading, 2)
            
            runtime_hours = self._calculate_runtime_for_period_with_filter(
                actual_device_id, module_tag_filter, start_time, end_time
            )
            
            return {
                "date": slice_obj.date,
                "start_time": format_datetime_without_microseconds(start_time),
                "end_time": format_datetime_without_microseconds(end_time),
                "start_reading": round(start_reading, 2) if start_reading is not None else None,
                "end_reading": round(end_reading, 2) if end_reading is not None else None,
                "consumption": consumption,
                "runtime_hours": runtime_hours,
                "feeding_amount": 0.0,
                "gas_consumption": 0.0
            }
        
        elif metric_type == "gas":
            # 燃气表保持原逻辑（device_id 一致）
            start_reading = self._get_gas_reading_at_time(
                actual_device_id, start_time
            )
            end_reading = self._get_gas_reading_at_time(
                actual_device_id, end_time
            )
            consumption = 0.0
            if end_reading is not None:
                start_value = start_reading if start_reading is not None else 0.0
                consumption = round(end_reading - start_value, 2)
                if consumption < 0:
                    consumption = round(end_reading, 2)
            
            runtime_hours = self._calculate_gas_meter_runtime(
                actual_device_id, start_time, end_time
            )
            
            return {
                "date": slice_obj.date,
                "start_time": format_datetime_without_microseconds(start_time),
                "end_time": format_datetime_without_microseconds(end_time),
                "start_reading": round(start_reading, 2) if start_reading is not None else None,
                "end_reading": round(end_reading, 2) if end_reading is not None else None,
                "consumption": 0.0,
                "runtime_hours": runtime_hours,
                "feeding_amount": 0.0,
                "gas_consumption": consumption
            }
        
        elif metric_type == "feeding":
            # 投料量保持原逻辑（device_id 一致）
            query = f'''
            from(bucket: "{self.bucket}")
                |> range(start: {start_time.isoformat()}, stop: {end_time.isoformat()})
                |> filter(fn: (r) => r["_measurement"] == "feeding_records")
                |> filter(fn: (r) => r["device_id"] == "{actual_device_id}")
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
                print(f"[WARN]  查询投料量失败: {str(e)}")
            
            return {
                "date": slice_obj.date,
                "start_time": format_datetime_without_microseconds(start_time),
                "end_time": format_datetime_without_microseconds(end_time),
                "start_reading": None,
                "end_reading": None,
                "consumption": 0.0,
                "runtime_hours": 0.0,
                "feeding_amount": round(feeding_amount, 2),
                "gas_consumption": 0.0
            }
        
        else:
            return {
                "date": slice_obj.date,
                "start_time": format_datetime_without_microseconds(start_time),
                "end_time": format_datetime_without_microseconds(end_time),
                "start_reading": None,
                "end_reading": None,
                "consumption": 0.0,
                "runtime_hours": 0.0,
                "feeding_amount": 0.0,
                "gas_consumption": 0.0
            }
    
    # ------------------------------------------------------------
    # [FIX] 新增：虚拟设备ID映射（兼容历史数据）
    # ------------------------------------------------------------
    def _map_virtual_device_to_actual(
        self,
        device_id: str,
        device_type: str
    ) -> tuple[str, str]:
        """将虚拟设备ID映射到实际数据库存储的ID
        
        Args:
            device_id: 虚拟设备ID (如 zone1, scr_1_pump)
            device_type: 虚拟设备类型
            
        Returns:
            (actual_device_id, module_tag_filter)
            
        映射规则:
        - zone1~zone6 -> (roller_kiln_1, zone1_meter~zone6_meter)
        - scr_1_pump -> (scr_1, meter)
        - scr_2_pump -> (scr_2, meter)
        - 其他设备 -> (device_id, None) 不需要过滤
        """
        # 辊道窑分区映射
        if device_type == "roller_kiln_zone":
            # zone1 -> (roller_kiln_1, zone1_meter)
            module_tag = f"{device_id}_meter"
            return ("roller_kiln_1", module_tag)
        
        # SCR 氨水泵映射
        elif device_type == "scr_pump":
            # scr_1_pump -> (scr_1, meter)
            actual_id = device_id.replace("_pump", "")
            return (actual_id, "meter")
        
        # 其他设备不需要映射
        else:
            return (device_id, None)
    
    # ------------------------------------------------------------
    # [FIX] 新增：带 module_tag 过滤的电量读数查询
    # ------------------------------------------------------------
    def _get_electricity_reading_at_time_with_filter(
        self,
        device_id: str,
        module_tag_filter: str,
        target_time: datetime
    ) -> Optional[float]:
        """查询指定时间点的电量读数（支持 module_tag 过滤）
        
        Args:
            device_id: 实际设备ID
            module_tag_filter: 模块标签过滤（如 zone1_meter, meter）
            target_time: 目标时间
            
        Returns:
            电量读数 (ImpEp) 或 None
        """
        # 构建查询（添加 module_tag 过滤）
        if module_tag_filter:
            query = f'''
            from(bucket: "{self.bucket}")
                |> range(start: {(target_time - timedelta(minutes=5)).isoformat()}, 
                         stop: {(target_time + timedelta(minutes=5)).isoformat()})
                |> filter(fn: (r) => r["_measurement"] == "sensor_data")
                |> filter(fn: (r) => r["device_id"] == "{device_id}")
                |> filter(fn: (r) => r["module_tag"] == "{module_tag_filter}")
                |> filter(fn: (r) => r["_field"] == "ImpEp")
                |> last()
            '''
        else:
            # 无需过滤，使用原逻辑
            return self._get_electricity_reading_at_time(device_id, target_time)
        
        try:
            result = self.query_api.query(query)
            for table in result:
                for record in table.records:
                    return record.get_value()
            return None
        except Exception as e:
            print(f"[WARN]  查询电量读数失败 {device_id}/{module_tag_filter}: {str(e)}")
            return None
    
    # ------------------------------------------------------------
    # [FIX] 新增：带 module_tag 过滤的运行时长计算
    # ------------------------------------------------------------
    def _calculate_runtime_for_period_with_filter(
        self,
        device_id: str,
        module_tag_filter: str,
        start_time: datetime,
        end_time: datetime
    ) -> float:
        """计算指定时间段的运行时长（支持 module_tag 过滤）
        
        Args:
            device_id: 实际设备ID
            module_tag_filter: 模块标签过滤
            start_time: 开始时间
            end_time: 结束时间
            
        Returns:
            运行时长（小时）
        """
        # 构建查询（添加 module_tag 过滤）
        if module_tag_filter:
            query = f'''
            from(bucket: "{self.bucket}")
                |> range(start: {start_time.isoformat()}, stop: {end_time.isoformat()})
                |> filter(fn: (r) => r["_measurement"] == "sensor_data")
                |> filter(fn: (r) => r["device_id"] == "{device_id}")
                |> filter(fn: (r) => r["module_tag"] == "{module_tag_filter}")
                |> filter(fn: (r) => r["_field"] == "Pt")
                |> filter(fn: (r) => r["_value"] > 0.01)
                |> count()
            '''
        else:
            # 无需过滤，使用原逻辑
            return self._calculate_runtime_for_period(device_id, start_time, end_time)
        
        try:
            result = self.query_api.query(query)
            count = 0
            for table in result:
                for record in table.records:
                    count = record.get_value()
                    break
            
            # 假设采样间隔为 6 秒
            runtime_hours = (count * 6) / 3600.0
            return round(runtime_hours, 2)
        
        except Exception as e:
            print(f"[WARN]  计算运行时长失败 {device_id}/{module_tag_filter}: {str(e)}")
            return 0.0
    
    # ------------------------------------------------------------
    # 核心优化 3: 内存缓存（完整天数据）
    # ------------------------------------------------------------
    def _get_cache_key(self, start_date: str, end_date: str) -> str:
        """生成缓存键"""
        key_str = f"{start_date}_{end_date}"
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def _get_from_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """从缓存获取数据"""
        return _memory_cache.get(cache_key)
    
    def _set_to_cache(self, cache_key: str, data: Dict[str, Any]):
        """存入缓存"""
        _memory_cache[cache_key] = data
        
        # 限制缓存大小（最多保留 100 个条目）
        if len(_memory_cache) > 100:
            # 删除最旧的条目
            oldest_key = next(iter(_memory_cache))
            del _memory_cache[oldest_key]
    
    # ------------------------------------------------------------
    # 主方法: export_comprehensive_v3() - 综合导出（终极优化版）
    # ------------------------------------------------------------
    def export_comprehensive_v3(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """综合导出所有设备的所有数据（终极优化版）
        
        核心优化:
        1. 批量查询预计算数据（一次查询所有设备）
        2. 并行计算不完整天（线程池）
        3. 内存缓存完整天数据
        
        性能提升: 10-20 倍
        """
        print(f" 开始综合导出（V3终极优化版）: {start_time} ~ {end_time}")
        
        # 1. 按自然日切分时间段
        slices = split_time_range_by_natural_days(start_time, end_time)
        full_day_slices = [s for s in slices if s.is_full_day]
        partial_day_slices = [s for s in slices if not s.is_full_day]
        
        print(f" 时间切分: {len(full_day_slices)} 个完整天, {len(partial_day_slices)} 个不完整天")
        
        # 2. 检查缓存（仅完整天）
        cache_key = None
        if full_day_slices and not partial_day_slices:
            start_date = full_day_slices[0].date
            end_date = full_day_slices[-1].date
            cache_key = self._get_cache_key(start_date, end_date)
            cached_data = self._get_from_cache(cache_key)
            
            if cached_data:
                print(f"[OK] 命中缓存，直接返回")
                return cached_data
        
        # 3. 批量查询完整天的预计算数据
        precomputed_data = {}
        if full_day_slices:
            start_date = datetime.strptime(full_day_slices[0].date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            end_date = datetime.strptime(full_day_slices[-1].date, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
            
            # 确保数据已补全
            self._get_summary_service().check_and_fill_missing_dates(end_date=end_date)
            
            # 批量查询
            precomputed_data = self._batch_query_daily_summary(start_date, end_date)
        
        # 4. 并行计算不完整天
        realtime_data = {}
        if partial_day_slices:
            # 定义所有设备配置
            device_configs = self._get_all_device_configs()
            realtime_data = self._parallel_calculate_partial_days(device_configs, partial_day_slices)
        
        # 5. 合并数据
        merged_data = self._merge_data(precomputed_data, realtime_data, slices)
        
        # 6. 格式化输出
        result = self._format_comprehensive_output(merged_data, start_time, end_time)
        
        # 7. 存入缓存（仅完整天）
        if cache_key:
            self._set_to_cache(cache_key, result)
        
        print(f"[OK] 综合导出完成（V3）: {result['total_devices']} 个设备")
        return result
    
    def _get_all_device_configs(self) -> List[Dict[str, str]]:
        """获取所有设备配置"""
        configs = []
        
        # 回转窑（料仓）
        hopper_ids = [
            "short_hopper_1", "short_hopper_2", "short_hopper_3", "short_hopper_4",
            "no_hopper_1", "no_hopper_2",
            "long_hopper_1", "long_hopper_2", "long_hopper_3"
        ]
        for hopper_id in hopper_ids:
            configs.append({
                "device_id": hopper_id,
                "device_type": "hopper",
                "metric_types": ["electricity", "feeding"]
            })
        
        # 辊道窑6个分区
        zone_ids = ["zone1", "zone2", "zone3", "zone4", "zone5", "zone6"]
        for zone_id in zone_ids:
            configs.append({
                "device_id": zone_id,
                "device_type": "roller_kiln_zone",
                "metric_types": ["electricity"]
            })
        
        # 辊道窑合计
        configs.append({
            "device_id": "roller_kiln_total",
            "device_type": "roller_kiln_total",
            "metric_types": ["electricity"]
        })
        
        # SCR燃气表
        configs.extend([
            {"device_id": "scr_1", "device_type": "scr_gas_meter", "metric_types": ["gas"]},
            {"device_id": "scr_2", "device_type": "scr_gas_meter", "metric_types": ["gas"]}
        ])
        
        # SCR氨水泵
        configs.extend([
            {"device_id": "scr_1_pump", "device_type": "scr_pump", "metric_types": ["electricity"]},
            {"device_id": "scr_2_pump", "device_type": "scr_pump", "metric_types": ["electricity"]}
        ])
        
        # 风机
        configs.extend([
            {"device_id": "fan_1", "device_type": "fan", "metric_types": ["electricity"]},
            {"device_id": "fan_2", "device_type": "fan", "metric_types": ["electricity"]}
        ])
        
        return configs
    
    def _merge_data(
        self,
        precomputed_data: Dict[str, Dict[str, List[Dict[str, Any]]]],
        realtime_data: Dict[str, Dict[str, List[Dict[str, Any]]]],
        slices: List[Any]
    ) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
        """合并预计算数据和实时数据"""
        merged = {}
        
        # 合并预计算数据
        for device_id, metrics in precomputed_data.items():
            if device_id not in merged:
                merged[device_id] = {}
            for metric_type, records in metrics.items():
                if metric_type not in merged[device_id]:
                    merged[device_id][metric_type] = []
                merged[device_id][metric_type].extend(records)
        
        # 合并实时数据
        for device_id, metrics in realtime_data.items():
            if device_id not in merged:
                merged[device_id] = {}
            for metric_type, records in metrics.items():
                if metric_type not in merged[device_id]:
                    merged[device_id][metric_type] = []
                merged[device_id][metric_type].extend(records)
        
        # 按日期排序
        for device_id in merged:
            for metric_type in merged[device_id]:
                merged[device_id][metric_type].sort(key=lambda x: x["date"])
        
        return merged
    
    def _format_comprehensive_output(
        self,
        merged_data: Dict[str, Dict[str, List[Dict[str, Any]]]],
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """格式化综合导出输出"""
        devices = []
        
        # [FIX] 生成完整的日期范围（确保每天都有记录）
        all_dates = []
        current_date = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = end_time.replace(hour=0, minute=0, second=0, microsecond=0)
        
        while current_date <= end_date:
            all_dates.append(current_date.strftime("%Y-%m-%d"))
            current_date += timedelta(days=1)
        
        print(f" 生成完整日期范围: {len(all_dates)} 天 ({all_dates[0]} ~ {all_dates[-1]})")
        
        # 获取所有设备配置
        device_configs = self._get_all_device_configs()
        
        for config in device_configs:
            device_id = config["device_id"]
            device_type = config["device_type"]
            
            # 获取该设备的所有数据
            device_data = merged_data.get(device_id, {})
            
            # [FIX] 初始化所有日期的记录（确保每天都有数据）
            daily_records_map = {}
            for date in all_dates:
                # [FIX] 为完整天填充默认时间（00:00:00 ~ 23:59:59）
                daily_records_map[date] = {
                    "date": date,
                    "start_time": f"{date}T00:00:00+00:00",  # 完整天的起始时间（无微秒）
                    "end_time": f"{date}T23:59:59+00:00",    # 完整天的终止时间（无微秒）
                    "gas_consumption": 0.0,
                    "feeding_amount": 0.0,
                    "electricity_consumption": 0.0,
                    "runtime_hours": 0.0
                }
            
            # 填充实际数据
            for metric_type, records in device_data.items():
                for record in records:
                    date = record["date"]
                    
                    # [FIX] 只更新存在于日期范围内的数据
                    if date in daily_records_map:
                        # [FIX] 更新起始/终止时间（不完整天使用实际时间，覆盖默认时间）
                        if record.get("start_time"):
                            daily_records_map[date]["start_time"] = record["start_time"]
                        if record.get("end_time"):
                            daily_records_map[date]["end_time"] = record["end_time"]
                        
                        # 更新指标数据
                        if metric_type == "electricity":
                            daily_records_map[date]["electricity_consumption"] = record.get("consumption", 0.0)
                            daily_records_map[date]["runtime_hours"] = record.get("runtime_hours", 0.0)
                        elif metric_type == "gas":
                            daily_records_map[date]["gas_consumption"] = record.get("gas_consumption", 0.0)
                            daily_records_map[date]["runtime_hours"] = record.get("runtime_hours", 0.0)
                        elif metric_type == "feeding":
                            daily_records_map[date]["feeding_amount"] = record.get("feeding_amount", 0.0)
            
            # [FIX] 转换为列表并按日期排序（确保时间顺序正确）
            daily_records = sorted(daily_records_map.values(), key=lambda x: x["date"])
            
            devices.append({
                "device_id": device_id,
                "device_type": device_type,
                "daily_records": daily_records
            })
        
        return {
            "start_time": format_datetime_without_microseconds(start_time),
            "end_time": format_datetime_without_microseconds(end_time),
            "total_devices": len(devices),
            "devices": devices
        }


    # ------------------------------------------------------------
    # 新增方法: export_runtime_v3() - 设备运行时长（V3优化版）
    # ------------------------------------------------------------
    def export_runtime_v3(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """设备运行时长（V3优化版）
        
        复用 export_comprehensive_v3 的数据，只提取运行时长字段
        """
        print(f" 开始设备运行时长（V3）: {start_time} ~ {end_time}")
        
        # 复用综合导出的数据
        comprehensive_data = self.export_comprehensive_v3(start_time, end_time)
        
        # 提取运行时长数据
        result = {
            "start_time": format_datetime_without_microseconds(start_time),
            "end_time": format_datetime_without_microseconds(end_time),
            "hoppers": [],
            "roller_kiln_zones": [],
            "roller_kiln_total": {},
            "scr_devices": [],
            "fan_devices": []
        }
        
        for device in comprehensive_data["devices"]:
            device_id = device["device_id"]
            device_type = device["device_type"]
            
            # 提取运行时长数据
            daily_records = []
            for record in device["daily_records"]:
                daily_records.append({
                    "date": record["date"],
                    "start_time": record["start_time"],
                    "end_time": record["end_time"],
                    "runtime_hours": record["runtime_hours"]
                })
            
            device_data = {
                "device_id": device_id,
                "device_type": device_type,
                "daily_records": daily_records
            }
            
            # 分类存储
            if device_type == "hopper":
                result["hoppers"].append(device_data)
            elif device_type == "roller_kiln_zone":
                result["roller_kiln_zones"].append(device_data)
            elif device_type == "roller_kiln_total":
                result["roller_kiln_total"] = device_data
            elif device_type == "scr_pump":
                result["scr_devices"].append(device_data)
            elif device_type == "fan":
                result["fan_devices"].append(device_data)
        
        print(f"[OK] 设备运行时长完成（V3）")
        return result
    
    # ------------------------------------------------------------
    # 新增方法: export_gas_v3() - 燃气消耗统计（V3优化版）
    # ------------------------------------------------------------
    def export_gas_v3(
        self,
        device_ids: List[str],
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """燃气消耗统计（V3优化版）
        
        复用 export_comprehensive_v3 的数据，只提取燃气消耗字段
        """
        print(f" 开始燃气消耗统计（V3）: {start_time} ~ {end_time}")
        
        # 复用综合导出的数据
        comprehensive_data = self.export_comprehensive_v3(start_time, end_time)
        
        # 提取燃气消耗数据
        result = {}
        
        for device in comprehensive_data["devices"]:
            device_id = device["device_id"]
            
            # 只处理指定的设备
            if device_id not in device_ids:
                continue
            
            # 提取燃气消耗数据
            daily_records = []
            for record in device["daily_records"]:
                daily_records.append({
                    "date": record["date"],
                    "start_time": record["start_time"],
                    "end_time": record["end_time"],
                    "consumption": record["gas_consumption"],
                    "runtime_hours": record["runtime_hours"]
                })
            
            result[device_id] = {
                "device_id": device_id,
                "daily_records": daily_records
            }
        
        print(f"[OK] 燃气消耗统计完成（V3）: {len(result)} 个设备")
        return result
    
    # ------------------------------------------------------------
    # 新增方法: export_feeding_v3() - 累计投料量（V3优化版）
    # ------------------------------------------------------------
    def export_feeding_v3(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """累计投料量（V3优化版）
        
        复用 export_comprehensive_v3 的数据，只提取投料量字段
        """
        print(f" 开始累计投料量（V3）: {start_time} ~ {end_time}")
        
        # 复用综合导出的数据
        comprehensive_data = self.export_comprehensive_v3(start_time, end_time)
        
        # 提取投料量数据
        result = {"hoppers": []}
        
        for device in comprehensive_data["devices"]:
            device_id = device["device_id"]
            device_type = device["device_type"]
            
            # 只处理料仓设备
            if device_type != "hopper":
                continue
            
            # 跳过无料仓的设备
            if device_id in ["no_hopper_1", "no_hopper_2"]:
                continue
            
            # 提取投料量数据
            daily_records = []
            for record in device["daily_records"]:
                daily_records.append({
                    "date": record["date"],
                    "start_time": record["start_time"],
                    "end_time": record["end_time"],
                    "feeding_amount": record["feeding_amount"]
                })
            
            result["hoppers"].append({
                "device_id": device_id,
                "daily_records": daily_records
            })
        
        print(f"[OK] 累计投料量完成（V3）: {len(result['hoppers'])} 个设备")
        return result
    
    # ------------------------------------------------------------
    # 新增方法: export_electricity_v3() - 电量统计（V3优化版）
    # ------------------------------------------------------------
    def export_electricity_v3(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """电量统计（V3优化版）
        
        复用 export_comprehensive_v3 的数据，只提取电量字段
        
        注意：需要从 daily_summary 表或实时计算中获取 start_reading 和 end_reading
        """
        print(f" 开始电量统计（V3）: {start_time} ~ {end_time}")
        
        # 1. 按自然日切分时间段
        slices = split_time_range_by_natural_days(start_time, end_time)
        full_day_slices = [s for s in slices if s.is_full_day]
        partial_day_slices = [s for s in slices if not s.is_full_day]
        
        # 2. 批量查询完整天的预计算数据
        precomputed_data = {}
        if full_day_slices:
            start_date = datetime.strptime(full_day_slices[0].date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            end_date = datetime.strptime(full_day_slices[-1].date, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
            
            # 确保数据已补全
            self._get_summary_service().check_and_fill_missing_dates(end_date=end_date)
            
            # 批量查询
            precomputed_data = self._batch_query_daily_summary(start_date, end_date)
        
        # 3. 并行计算不完整天
        realtime_data = {}
        if partial_day_slices:
            # 只查询有电量数据的设备
            device_configs = [
                config for config in self._get_all_device_configs()
                if "electricity" in config["metric_types"]
            ]
            realtime_data = self._parallel_calculate_partial_days(device_configs, partial_day_slices)
        
        # 4. 合并数据
        merged_data = self._merge_data(precomputed_data, realtime_data, slices)
        
        # 5. 格式化输出（包含 start_reading 和 end_reading）
        result = {
            "start_time": format_datetime_without_microseconds(start_time),
            "end_time": format_datetime_without_microseconds(end_time),
            "hoppers": [],
            "roller_kiln_zones": [],
            "roller_kiln_total": {},
            "scr_devices": [],
            "fan_devices": []
        }
        
        # 生成完整的日期范围
        all_dates = []
        current_date = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date_obj = end_time.replace(hour=0, minute=0, second=0, microsecond=0)
        
        while current_date <= end_date_obj:
            all_dates.append(current_date.strftime("%Y-%m-%d"))
            current_date += timedelta(days=1)
        
        # 获取所有有电量数据的设备
        device_configs = [
            config for config in self._get_all_device_configs()
            if "electricity" in config["metric_types"]
        ]
        
        for config in device_configs:
            device_id = config["device_id"]
            device_type = config["device_type"]
            
            # 获取该设备的电量数据
            device_data = merged_data.get(device_id, {}).get("electricity", [])
            
            # 初始化所有日期的记录
            daily_records_map = {}
            for date in all_dates:
                daily_records_map[date] = {
                    "date": date,
                    "start_time": f"{date}T00:00:00+00:00",
                    "end_time": f"{date}T23:59:59+00:00",
                    "start_reading": 0.0,
                    "end_reading": 0.0,
                    "consumption": 0.0,
                    "runtime_hours": 0.0
                }
            
            # 填充实际数据
            for record in device_data:
                date = record["date"]
                if date in daily_records_map:
                    # 更新时间
                    if record.get("start_time"):
                        daily_records_map[date]["start_time"] = record["start_time"]
                    if record.get("end_time"):
                        daily_records_map[date]["end_time"] = record["end_time"]
                    
                    # 更新读数和消耗
                    daily_records_map[date]["start_reading"] = record.get("start_reading", 0.0) or 0.0
                    daily_records_map[date]["end_reading"] = record.get("end_reading", 0.0) or 0.0
                    daily_records_map[date]["consumption"] = record.get("consumption", 0.0)
                    daily_records_map[date]["runtime_hours"] = record.get("runtime_hours", 0.0)
            
            # 转换为列表并排序
            daily_records = sorted(daily_records_map.values(), key=lambda x: x["date"])
            
            device_data_obj = {
                "device_id": device_id,
                "device_type": device_type,
                "daily_records": daily_records
            }
            
            # 分类存储
            if device_type == "hopper":
                result["hoppers"].append(device_data_obj)
            elif device_type == "roller_kiln_zone":
                result["roller_kiln_zones"].append(device_data_obj)
            elif device_type == "roller_kiln_total":
                result["roller_kiln_total"] = device_data_obj
            elif device_type == "scr_pump":
                result["scr_devices"].append(device_data_obj)
            elif device_type == "fan":
                result["fan_devices"].append(device_data_obj)
        
        print(f"[OK] 电量统计完成（V3）")
        return result


# ------------------------------------------------------------
# 单例获取函数
# ------------------------------------------------------------


# ------------------------------------------------------------
# 单例获取函数
# ------------------------------------------------------------
def get_export_service() -> DataExportService:
    """获取数据导出服务单例"""
    global _export_service_instance
    if _export_service_instance is None:
        _export_service_instance = DataExportService()
    return _export_service_instance


# [FIX] 兼容旧导入名称
get_export_service_v3 = get_export_service
