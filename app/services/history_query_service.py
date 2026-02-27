# ============================================================
# 文件说明: history_query_service.py - 历史数据查询服务
# ============================================================
# 方法列表:
# 1. query_device_list()          - 查询设备列表
# 2. query_device_realtime()      - 查询设备最新数据
# 3. query_device_history()       - 查询设备历史数据
# 4. query_temperature_history()  - 查询温度历史
# 5. query_power_history()        - 查询功率历史
# 6. query_weight_history()       - 查询称重历史
# 7. query_multi_device_compare() - 多设备对比查询
# 8. query_db_devices()           - 按DB块查询设备
# ============================================================

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from influxdb_client import InfluxDBClient
from functools import lru_cache

logger = logging.getLogger(__name__)

from config import get_settings
from app.core.influxdb import get_influx_client
from app.tools.timezone_tools import to_beijing, beijing_isoformat, BEIJING_TZ

settings = get_settings()


# [FIX] 单例实例
_history_service_instance: Optional['HistoryQueryService'] = None


class HistoryQueryService:
    """历史数据查询服务（单例模式）"""
    
    def __init__(self):
        self._client = None  # [FIX] 延迟初始化
        self._query_api = None
        # [CRITICAL] 使用环境变量配置的 bucket
        self.bucket = settings.influx_bucket
        self.org = settings.influx_org
    
    @property
    def client(self):
        """延迟获取 InfluxDB 客户端"""
        if self._client is None:
            self._client = get_influx_client()
        return self._client
    
    @property
    def query_api(self):
        """延迟获取 query_api，确保使用最新的 client"""
        # [FIX] 每次都从当前 client 获取，避免旧 client 过期
        return self.client.query_api()
    
    # ------------------------------------------------------------
    # 0. get_latest_db_timestamp() - 获取数据库中最新数据的时间戳
    # ------------------------------------------------------------
    def get_latest_db_timestamp(self) -> Optional[datetime]:
        """获取数据库中最新数据的时间戳
        
        Returns:
            最新数据的时间戳（UTC时间），如果没有数据则返回None
        """
        query = f'''
        from(bucket: "{self.bucket}")
            |> range(start: -30d)
            |> filter(fn: (r) => r["_measurement"] == "sensor_data")
            |> last()
            |> keep(columns: ["_time"])
        '''
        
        try:
            result = self.query_api.query(query)
            latest_time = None
            
            for table in result:
                for record in table.records:
                    timestamp = record.get_time()
                    if latest_time is None or timestamp > latest_time:
                        latest_time = timestamp
            
            return latest_time
        except Exception as e:
            logger.warning("[History] 获取最新时间戳失败: %s", e)
            return None
    
    # ------------------------------------------------------------
    # 0.1 query_weight_at_timestamp() - 查询指定时间的重量
    # ------------------------------------------------------------
    def query_weight_at_timestamp(self, device_id: str, target_time: datetime, window_seconds: int = 60) -> Optional[float]:
        """查询指定时间点附近的重量数据
        
        Args:
            device_id: 设备ID
            target_time: 目标时间
            window_seconds: 搜索窗口大小（秒），默认前后30秒
            
        Returns:
            查询到的重量值，如果没有则返回None
        """
        # 计算查询时间范围 [target - window, target + window]
        start_time = target_time - timedelta(seconds=window_seconds)
        end_time = target_time + timedelta(seconds=window_seconds)
        
        query = f'''
        from(bucket: "{self.bucket}")
            |> range(start: {start_time.isoformat()}, stop: {end_time.isoformat()})
            |> filter(fn: (r) => r["_measurement"] == "sensor_data")
            |> filter(fn: (r) => r["device_id"] == "{device_id}")
            |> filter(fn: (r) => r["_field"] == "weight")
            |> filter(fn: (r) => r["module_type"] == "WeighSensor")
            |> first()
            |> yield(name: "weight")
        '''
        
        try:
            result = self.query_api.query(query)
            
            # 解析结果
            for table in result:
                for record in table.records:
                    # 返回第一个匹配的值
                    val = record.get_value()
                    if val is not None:
                        return float(val)
            
            return None
        except Exception as e:
            # 静默失败，避免刷屏日志
            # print(f"[WARN]  查询历史重量失败: {str(e)}")
            return None

    # ------------------------------------------------------------
    # 1. query_device_list() - 查询设备列表
    # ------------------------------------------------------------
    def query_device_list(self, device_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """查询所有设备列表（永远不返回空列表）
        
        Args:
            device_type: 可选，按设备类型筛选 (如 short_hopper, roller_kiln)
            
        Returns:
            [
                {"device_id": "short_hopper_1", "device_type": "short_hopper", "db_number": "6"},
                ...
            ]
        """
        # 使用更简单的查询方式，避免 distinct 类型冲突
        # 修复: 保留 _value 列，避免 "no column _value exists" 错误
        filter_str = 'r["_measurement"] == "sensor_data"'
        if device_type:
            filter_str += f' and r["device_type"] == "{device_type}"'
        
        query = f'''
        from(bucket: "{self.bucket}")
            |> range(start: -24h)
            |> filter(fn: (r) => {filter_str})
            |> keep(columns: ["device_id", "device_type", "db_number", "_value", "_time"])
            |> group(columns: ["device_id", "device_type", "db_number"])
            |> first()
        '''
        
        try:
            result = self.query_api.query(query)
            
            devices = {}
            for table in result:
                for record in table.records:
                    device_id = record.values.get('device_id')
                    if device_id and device_id not in devices:
                        devices[device_id] = {
                            'device_id': device_id,
                            'device_type': record.values.get('device_type', ''),
                            'db_number': record.values.get('db_number', '')
                        }
            
            device_list = list(devices.values())
            
            # 如果数据库没有数据，返回兜底的设备列表
            if not device_list:
                device_list = self._get_fallback_device_list(device_type)
            
            return device_list
        except Exception as e:
            # 查询失败时，返回兜底列表
            logger.warning("[History] 设备列表查询失败: %s, 返回兗底数据", e)
            return self._get_fallback_device_list(device_type)
    
    def _get_fallback_device_list(self, device_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """返回兜底的设备列表，确保永远不为空"""
        all_devices = [
            # 短料仓 (4个)
            {"device_id": "short_hopper_1", "device_type": "short_hopper", "db_number": "8"},
            {"device_id": "short_hopper_2", "device_type": "short_hopper", "db_number": "8"},
            {"device_id": "short_hopper_3", "device_type": "short_hopper", "db_number": "8"},
            {"device_id": "short_hopper_4", "device_type": "short_hopper", "db_number": "8"},
            # 无料仓 (2个)
            {"device_id": "no_hopper_1", "device_type": "no_hopper", "db_number": "8"},
            {"device_id": "no_hopper_2", "device_type": "no_hopper", "db_number": "8"},
            # 长料仓 (3个)
            {"device_id": "long_hopper_1", "device_type": "long_hopper", "db_number": "8"},
            {"device_id": "long_hopper_2", "device_type": "long_hopper", "db_number": "8"},
            {"device_id": "long_hopper_3", "device_type": "long_hopper", "db_number": "8"},
            # 辊道窑 (1个)
            {"device_id": "roller_kiln_1", "device_type": "roller_kiln", "db_number": "9"},
            # SCR (2个)
            {"device_id": "scr_1", "device_type": "scr", "db_number": "10"},
            {"device_id": "scr_2", "device_type": "scr", "db_number": "10"},
            # 风机 (2个)
            {"device_id": "fan_1", "device_type": "fan", "db_number": "10"},
            {"device_id": "fan_2", "device_type": "fan", "db_number": "10"},
        ]
        
        if device_type:
            return [d for d in all_devices if d["device_type"] == device_type]
        return all_devices
    
    # ------------------------------------------------------------
    # 2. query_device_realtime() - 查询设备最新数据
    # ------------------------------------------------------------
    def query_device_realtime(self, device_id: str) -> Dict[str, Any]:
        """查询设备所有传感器的最新数据
        
        Args:
            device_id: 设备ID (如 short_hopper_1)
            
        Returns:
            {
                "device_id": "short_hopper_1",
                "timestamp": "2025-12-09T10:00:00Z",
                "modules": {
                    "meter": {"Pt": 120.5, "ImpEp": 1234.5, ...},
                    "temp": {"temperature": 85.5},
                    "weight": {"weight": 1234.5, "feed_rate": 12.3}
                }
            }
        
        说明:
            - 查询数据库中的最新数据，不限时间范围
            - 使用 -30d 范围确保能找到数据（但只取最新的一条）
        """
        # 查询最近30天的最新数据（确保能找到数据，但只取最新）
        query = f'''
        from(bucket: "{self.bucket}")
            |> range(start: -30d)
            |> filter(fn: (r) => r["device_id"] == "{device_id}")
            |> last()
        '''
        
        result = self.query_api.query(query)
        
        # 解析结果，按module_tag分组
        modules_data = {}
        latest_time = None
        
        for table in result:
            for record in table.records:
                module_tag = record.values.get('module_tag', 'unknown')
                field_name = record.get_field()
                field_value = record.get_value()
                timestamp = record.get_time()
                
                if module_tag not in modules_data:
                    modules_data[module_tag] = {
                        'module_type': record.values.get('module_type', ''),
                        'fields': {}
                    }
                
                modules_data[module_tag]['fields'][field_name] = field_value
                
                if latest_time is None or timestamp > latest_time:
                    latest_time = timestamp
        
        return {
            'device_id': device_id,
            'timestamp': to_beijing(latest_time).isoformat() if latest_time else None,
            'modules': modules_data
        }
    
    # ------------------------------------------------------------
    # 2. query_device_history() - 查询设备历史数据（支持动态聚合）
    # ------------------------------------------------------------
    def query_device_history(
        self,
        device_id: str,
        start: datetime,
        end: datetime,
        module_type: Optional[str] = None,
        module_tag: Optional[str] = None,
        fields: Optional[List[str]] = None,
        interval: Optional[str] = None,
        auto_interval: bool = True
    ) -> List[Dict[str, Any]]:
        """查询设备历史数据（支持动态聚合间隔）
        
        Args:
            device_id: 设备ID
            start: 开始时间
            end: 结束时间
            module_type: 可选，过滤模块类型 (如 TemperatureSensor)
            module_tag: 可选，过滤模块标签 (如 temp, zone1_temp)
            fields: 可选，指定字段列表 (如 ["Temperature", "Pt"])
            interval: 聚合间隔 (如 1m, 5m, 1h)，如果为 None 则自动计算
            auto_interval: 是否自动计算最佳聚合间隔（默认 True）
            
        Returns:
            [
                {
                    "time": "2025-12-09T10:00:00Z",
                    "module_tag": "temp",
                    "Temperature": 85.5,
                    "SetPoint": 90.0
                },
                ...
            ]
        """
        # 构建过滤条件
        filters = [f'r["device_id"] == "{device_id}"']
        
        if module_type:
            filters.append(f'r["module_type"] == "{module_type}"')
        
        if module_tag:
            filters.append(f'r["module_tag"] == "{module_tag}"')
        
        if fields:
            field_conditions = ' or '.join([f'r["_field"] == "{f}"' for f in fields])
            filters.append(f'({field_conditions})')
        
        filter_str = ' and '.join(filters)
        
        # [FIX] 修复时区转换逻辑：检查输入时间是否已有时区信息
        def to_utc(dt: datetime) -> datetime:
            if dt.tzinfo is None:
                # 无时区信息，默认视为北京时间
                dt = dt.replace(tzinfo=BEIJING_TZ)
            
            # 转换为UTC
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        
        start_utc = to_utc(start)
        end_utc = to_utc(end)
        
        # [NEW] 动态计算最佳聚合间隔
        if auto_interval and interval is None:
            interval = self._calculate_optimal_interval(start_utc, end_utc)
        elif interval is None:
            interval = "1m"  # 默认值
        
        query = f'''
        from(bucket: "{self.bucket}")
            |> range(start: {start_utc.isoformat()}Z, stop: {end_utc.isoformat()}Z)
            |> filter(fn: (r) => r["_measurement"] == "sensor_data")
            |> filter(fn: (r) => {filter_str})
            |> aggregateWindow(every: {interval}, fn: mean, createEmpty: false)
            |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        '''
        
        result = self.query_api.query(query)
        
        # 解析结果
        data = []
        for table in result:
            for record in table.records:
                row = {
                    'time': to_beijing(record.get_time()).isoformat(),
                    'module_tag': record.values.get('module_tag', ''),
                    'module_type': record.values.get('module_type', '')
                }
                
                # 添加所有字段值
                for key, value in record.values.items():
                    if not key.startswith('_') and key not in ['device_id', 'device_type', 'module_type', 'module_tag', 'db_number', 'result', 'table']:
                        row[key] = value
                
                data.append(row)
        
        return data
    
    # ------------------------------------------------------------
    # 3. query_temperature_history() - 查询温度历史
    # ------------------------------------------------------------
    def query_temperature_history(
        self,
        device_id: str,
        start: datetime,
        end: datetime,
        module_tag: Optional[str] = None,
        interval: str = "1m"
    ) -> List[Dict[str, Any]]:
        """查询设备温度历史数据（便捷方法）"""
        # [FIX] 存储字段为 temperature (lowercase)，converter_temp.py 输出为小写
        return self.query_device_history(
            device_id=device_id,
            start=start,
            end=end,
            module_type="TemperatureSensor",
            module_tag=module_tag,
            fields=["temperature"],
            interval=interval
        )
    
    # ------------------------------------------------------------
    # 5. query_power_history() - 查询功率和电流历史
    # ------------------------------------------------------------
    def query_power_history(
        self,
        device_id: str,
        start: datetime,
        end: datetime,
        module_tag: Optional[str] = None,
        interval: str = "1m"
    ) -> List[Dict[str, Any]]:
        """查询设备功率/电流历史数据（便捷方法）
        
        存储字段: Pt (功率), ImpEp (能耗), Ua_0 (A相电压), I_0/I_1/I_2 (三相电流)
        """
        # [FIX] 存储字段为 Pt, ImpEp, Ua_0, I_0, I_1, I_2 (convert_for_storage 输出)
        # Uab_0/1/2 (线电压) 不存储，不要查询
        return self.query_device_history(
            device_id=device_id,
            start=start,
            end=end,
            module_type="ElectricityMeter",
            module_tag=module_tag,
            fields=["Pt", "ImpEp", "Ua_0", "I_0", "I_1", "I_2"],
            interval=interval
        )

    # ------------------------------------------------------------
    # 6. query_feeding_history() - 查询投料记录
    # ------------------------------------------------------------
    def query_feeding_history(
        self,
        device_id: str,
        start: datetime,
        end: datetime,
        limit: int = 5000
    ) -> List[Dict[str, Any]]:
        """查询自动投料分析记录
        
        Args:
           device_id: 设备ID
           start: 开始时间 (Naive Beijing Time or Aware)
           end: 结束时间
           limit: 返回记录数限制
        
        Returns:
            [{ "time": "...", "added_weight": 10.5, "device_id": "..." }, ...]
        """
        # 统一时区处理逻辑 (参考 query_device_history)
        def to_utc(dt: datetime) -> datetime:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=BEIJING_TZ)
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        
        start_utc = to_utc(start)
        end_utc = to_utc(end)

        # 构造 Flux 查询 (倒序取最新)
        # [FIX] 兼容新旧字段名: v5.0 写 "amount", 旧版/backfill 写 "added_weight"
        query = f'''
        from(bucket: "{self.bucket}")
            |> range(start: {start_utc.isoformat()}Z, stop: {end_utc.isoformat()}Z)
            |> filter(fn: (r) => r["_measurement"] == "feeding_records")
            |> filter(fn: (r) => r["device_id"] == "{device_id}")
            |> filter(fn: (r) => r["_field"] == "amount" or r["_field"] == "added_weight")
            |> sort(columns: ["_time"], desc: true)
            |> limit(n: {limit})
        '''
        
        result = self.query_api.query(query)
        records = []
        for table in result:
            for record in table.records:
                records.append({
                    "time": to_beijing(record.get_time()).isoformat(),
                    "amount": record.get_value(),  # 统一使用 amount
                    "device_id": device_id
                })
        
        # [CRITICAL] 按时间升序排列 (Oldest -> Newest)
        # 前端绘制曲线时需要时间按照顺序，否则会出现回勾
        records.sort(key=lambda x: x["time"])
        
        return records

    # ------------------------------------------------------------
    # 6.1 query_feeding_cumulative_history() - 查询下料速度/投料总量历史
    # ------------------------------------------------------------
    def query_feeding_cumulative_history(
        self,
        device_id: str,
        start: datetime,
        end: datetime,
        fields: Optional[List[str]] = None,
        interval: Optional[str] = None,
        auto_interval: bool = True,
    ) -> List[Dict[str, Any]]:
        """查询 feeding_cumulative measurement 的历史数据
        
        存储了 display_feed_rate (下料速度) 和 feeding_total (投料总量)
        
        Args:
            device_id: 设备ID
            start: 开始时间 (Naive Beijing Time or Aware)
            end: 结束时间
            fields: 查询字段, 默认 ["display_feed_rate", "feeding_total"]
            interval: 聚合间隔
            auto_interval: 是否自动计算间隔
            
        Returns:
            [{ "time": "...", "display_feed_rate": 12.5, "feeding_total": 350.0 }, ...]
        """
        if fields is None:
            fields = ["display_feed_rate", "feeding_total"]
        
        # 时区转换
        def to_utc(dt: datetime) -> datetime:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=BEIJING_TZ)
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        
        start_utc = to_utc(start)
        end_utc = to_utc(end)
        
        # 计算聚合间隔
        if auto_interval and interval is None:
            interval = self._calculate_optimal_interval(start_utc, end_utc)
        elif interval is None:
            interval = "1m"
        
        # 构建字段过滤
        field_conditions = ' or '.join([f'r["_field"] == "{f}"' for f in fields])
        
        query = f'''
        from(bucket: "{self.bucket}")
            |> range(start: {start_utc.isoformat()}Z, stop: {end_utc.isoformat()}Z)
            |> filter(fn: (r) => r["_measurement"] == "feeding_cumulative")
            |> filter(fn: (r) => r["device_id"] == "{device_id}")
            |> filter(fn: (r) => {field_conditions})
            |> aggregateWindow(every: {interval}, fn: mean, createEmpty: false)
            |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        '''
        
        result = self.query_api.query(query)
        
        data = []
        for table in result:
            for record in table.records:
                row = {"time": to_beijing(record.get_time()).isoformat()}
                for f in fields:
                    val = record.values.get(f)
                    if val is not None:
                        row[f] = round(float(val), 2) if isinstance(val, (int, float)) else val
                data.append(row)
        
        # 按时间升序
        data.sort(key=lambda x: x["time"])
        # [FIX] 返回 (data, interval) tuple，调用方需解包
        return data, interval
    
    # ------------------------------------------------------------
    # 6. query_weight_history() - 查询称重历史
    # ------------------------------------------------------------
    def query_weight_history(
        self,
        device_id: str,
        start: datetime,
        end: datetime,
        module_tag: Optional[str] = None,
        interval: str = "1m"
    ) -> List[Dict[str, Any]]:
        """查询设备称重历史数据（便捷方法）
        
        存储字段: weight (实时重量), is_stable (稳定标志), is_overload (超载标志)
        """
        # [FIX] 存储字段为 weight (converter_weight.py 输出)，不是 GrossWeight/NetWeight
        return self.query_device_history(
            device_id=device_id,
            start=start,
            end=end,
            module_type="WeighSensor",
            module_tag=module_tag,
            fields=["weight"],
            interval=interval
        )
    
    # ------------------------------------------------------------
    # 7. query_multi_device_compare() - 多设备对比查询
    # ------------------------------------------------------------
    def query_multi_device_compare(
        self,
        device_ids: List[str],
        field: str,
        start: datetime,
        end: datetime,
        module_type: Optional[str] = None,
        interval: str = "5m"
    ) -> List[Dict[str, Any]]:
        """多设备字段对比查询
        
        Args:
            device_ids: 设备ID列表
            field: 对比字段 (如 Temperature, Pt)
            start: 开始时间
            end: 结束时间
            module_type: 可选，过滤模块类型
            interval: 聚合间隔
            
        Returns:
            [
                {
                    "time": "2025-12-09T10:00:00Z",
                    "short_hopper_1": 85.5,
                    "short_hopper_2": 87.2,
                    "short_hopper_3": 84.8
                },
                ...
            ]
        """
        # 构建设备过滤条件
        device_conditions = ' or '.join([f'r["device_id"] == "{did}"' for did in device_ids])
        
        filters = [f'({device_conditions})', f'r["_field"] == "{field}"']
        
        if module_type:
            filters.append(f'r["module_type"] == "{module_type}"')
        
        filter_str = ' and '.join(filters)
        
        # [FIX] 修复时区转换逻辑：检查输入时间是否已有时区信息
        # 如果无时区信息，默认视为北京时间 (因为前端通常传北京时间)
        if start.tzinfo is None:
            start = start.replace(tzinfo=BEIJING_TZ)
        start_utc = start.astimezone(timezone.utc).replace(tzinfo=None)

        if end.tzinfo is None:
            end = end.replace(tzinfo=BEIJING_TZ)
        end_utc = end.astimezone(timezone.utc).replace(tzinfo=None)
        
        query = f'''
        from(bucket: "{self.bucket}")
            |> range(start: {start_utc.isoformat()}Z, stop: {end_utc.isoformat()}Z)
            |> filter(fn: (r) => {filter_str})
            |> aggregateWindow(every: {interval}, fn: mean, createEmpty: false)
            |> pivot(rowKey:["_time"], columnKey: ["device_id"], valueColumn: "_value")
        '''
        
        result = self.query_api.query(query)
        
        # 解析结果
        data = []
        for table in result:
            for record in table.records:
                row = {'time': to_beijing(record.get_time()).isoformat()}
                
                # 添加每个设备的值
                for key, value in record.values.items():
                    if key in device_ids:
                        row[key] = value
                
                data.append(row)
        
        return data
    
    # ------------------------------------------------------------
    # 8. query_db_devices() - 按DB块查询设备
    # ------------------------------------------------------------
    def query_db_devices(self, db_number: str) -> List[Dict[str, Any]]:
        """查询指定DB块的所有设备
        
        Args:
            db_number: DB块号 (如 "6", "7", "8")
            
        Returns:
            设备列表
        """
        query = f'''
        from(bucket: "{self.bucket}")
            |> range(start: -24h)
            |> filter(fn: (r) => r["db_number"] == "{db_number}")
            |> group(columns: ["device_id", "device_type"])
            |> distinct(column: "device_id")
        '''
        
        result = self.query_api.query(query)
        
        devices = {}
        for table in result:
            for record in table.records:
                device_id = record.values.get('device_id')
                if device_id and device_id not in devices:
                    devices[device_id] = {
                        'device_id': device_id,
                        'device_type': record.values.get('device_type', ''),
                        'db_number': db_number
                    }
        
        return list(devices.values())
    
    # ------------------------------------------------------------
    # 9. _calculate_optimal_interval() - 动态计算最佳聚合间隔
    # ------------------------------------------------------------
    def _calculate_optimal_interval(self, start: datetime, end: datetime) -> str:
        """根据时间范围动态计算最佳聚合间隔
        
        目标：保持返回的数据点数在 40-150 之间，理想值为 80 点
        
        Args:
            start: 开始时间（UTC）
            end: 结束时间（UTC）
            
        Returns:
            聚合间隔字符串（如 "5s", "1m", "5m", "1h"）
        """
        # 目标数据点数
        target_points = 80
        min_points = 40
        max_points = 150
        
        # 有效的聚合间隔（秒）
        valid_intervals = [
            5, 10, 15, 30,           # 秒级
            60, 120, 180, 300, 600, 900, 1800,  # 分钟级
            3600, 7200, 14400, 21600, 43200,    # 小时级
            86400, 172800, 259200, 604800       # 天级
        ]
        
        # 计算时间范围（秒）
        duration = (end - start).total_seconds()
        
        if duration <= 0:
            return "5s"
        
        # 计算理想间隔
        ideal_interval = duration / target_points
        
        # 找到最接近理想值且在合理范围内的间隔
        best_interval = valid_intervals[0]
        min_diff = float('inf')
        
        for interval in valid_intervals:
            estimated_points = duration / interval
            
            # 优先选择在合理范围内的间隔
            if min_points <= estimated_points <= max_points:
                diff = abs(estimated_points - target_points)
                if diff < min_diff:
                    min_diff = diff
                    best_interval = interval
        
        # 如果没有找到合理范围内的，选择最接近理想值的
        if min_diff == float('inf'):
            min_diff = float('inf')
            for interval in valid_intervals:
                diff = abs(interval - ideal_interval)
                if diff < min_diff:
                    min_diff = diff
                    best_interval = interval
        
        # 格式化为 InfluxDB 间隔字符串
        return self._format_interval(best_interval)
    
    def _format_interval(self, seconds: int) -> str:
        """将秒数格式化为 InfluxDB 间隔字符串"""
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            return f"{seconds // 60}m"
        elif seconds < 86400:
            return f"{seconds // 3600}h"
        else:
            return f"{seconds // 86400}d"


# ============================================================
# [FIX] 获取单例服务实例
# ============================================================
def get_history_service() -> HistoryQueryService:
    """获取历史查询服务单例"""
    global _history_service_instance
    if _history_service_instance is None:
        _history_service_instance = HistoryQueryService()
    return _history_service_instance

