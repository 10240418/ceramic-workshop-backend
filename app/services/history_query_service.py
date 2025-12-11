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

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from influxdb_client import InfluxDBClient
from functools import lru_cache

from config import get_settings
from app.core.influxdb import get_influx_client

settings = get_settings()


class HistoryQueryService:
    """历史数据查询服务"""
    
    def __init__(self):
        self.client = get_influx_client()
        self.query_api = self.client.query_api()
        self.bucket = settings.influx_bucket
    
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
        filter_str = 'r["_measurement"] == "sensor_data"'
        if device_type:
            filter_str += f' and r["device_type"] == "{device_type}"'
        
        query = f'''
        from(bucket: "{self.bucket}")
            |> range(start: -24h)
            |> filter(fn: (r) => {filter_str})
            |> group(columns: ["device_id", "device_type", "db_number"])
            |> distinct(column: "device_id")
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
            print(f"⚠️  设备列表查询失败: {str(e)}，返回兜底数据")
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
                    "meter": {"Uab_0": 380.5, "I_0": 12.3, ...},
                    "temp": {"Temperature": 85.5, "SetPoint": 90.0},
                    "weight": {"GrossWeight": 1234.5, ...}
                }
            }
        """
        # 查询最近24小时的最新数据
        query = f'''
        from(bucket: "{self.bucket}")
            |> range(start: -24h)
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
            'timestamp': latest_time.isoformat() if latest_time else None,
            'modules': modules_data
        }
    
    # ------------------------------------------------------------
    # 2. query_device_history() - 查询设备历史数据
    # ------------------------------------------------------------
    def query_device_history(
        self,
        device_id: str,
        start: datetime,
        end: datetime,
        module_type: Optional[str] = None,
        module_tag: Optional[str] = None,
        fields: Optional[List[str]] = None,
        interval: str = "1m"
    ) -> List[Dict[str, Any]]:
        """查询设备历史数据
        
        Args:
            device_id: 设备ID
            start: 开始时间
            end: 结束时间
            module_type: 可选，过滤模块类型 (如 TemperatureSensor)
            module_tag: 可选，过滤模块标签 (如 temp, zone1_temp)
            fields: 可选，指定字段列表 (如 ["Temperature", "Pt"])
            interval: 聚合间隔 (如 1m, 5m, 1h)
            
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
        
        query = f'''
        from(bucket: "{self.bucket}")
            |> range(start: {start.isoformat()}Z, stop: {end.isoformat()}Z)
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
                    'time': record.get_time().isoformat(),
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
        return self.query_device_history(
            device_id=device_id,
            start=start,
            end=end,
            module_type="TemperatureSensor",
            module_tag=module_tag,
            fields=["Temperature", "SetPoint"],
            interval=interval
        )
    
    # ------------------------------------------------------------
    # 5. query_power_history() - 查询功率历史
    # ------------------------------------------------------------
    def query_power_history(
        self,
        device_id: str,
        start: datetime,
        end: datetime,
        module_tag: Optional[str] = None,
        interval: str = "1m"
    ) -> List[Dict[str, Any]]:
        """查询设备功率历史数据（便捷方法）"""
        return self.query_device_history(
            device_id=device_id,
            start=start,
            end=end,
            module_type="ElectricityMeter",
            module_tag=module_tag,
            fields=["Pt", "Uab_0", "Uab_1", "Uab_2", "I_0", "I_1", "I_2"],
            interval=interval
        )
    
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
        """查询设备称重历史数据（便捷方法）"""
        return self.query_device_history(
            device_id=device_id,
            start=start,
            end=end,
            module_type="WeighSensor",
            module_tag=module_tag,
            fields=["GrossWeight", "NetWeight", "TareWeight"],
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
        
        query = f'''
        from(bucket: "{self.bucket}")
            |> range(start: {start.isoformat()}Z, stop: {end.isoformat()}Z)
            |> filter(fn: (r) => {filter_str})
            |> aggregateWindow(every: {interval}, fn: mean, createEmpty: false)
            |> pivot(rowKey:["_time"], columnKey: ["device_id"], valueColumn: "_value")
        '''
        
        result = self.query_api.query(query)
        
        # 解析结果
        data = []
        for table in result:
            for record in table.records:
                row = {'time': record.get_time().isoformat()}
                
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


# ============================================================
# 使用示例
# ============================================================
if __name__ == "__main__":
    service = HistoryQueryService()
    
    # 测试查询实时数据
    print("=== 测试查询实时数据 ===")
    realtime = service.query_device_realtime("short_hopper_1")
    print(f"设备: {realtime['device_id']}")
    print(f"时间: {realtime['timestamp']}")
    print(f"模块数: {len(realtime['modules'])}")
    
    # 测试查询历史温度
    print("\n=== 测试查询历史温度 ===")
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=1)
    
    history = service.query_temperature_history(
        device_id="roller_kiln_1",
        start=start_time,
        end=end_time,
        module_tag="zone1_temp",
        interval="5m"
    )
    print(f"查询到 {len(history)} 条数据")
    
    # 测试多设备对比
    print("\n=== 测试多设备温度对比 ===")
    compare = service.query_multi_device_compare(
        device_ids=["short_hopper_1", "short_hopper_2", "short_hopper_3"],
        field="Temperature",
        start=start_time,
        end=end_time,
        module_type="TemperatureSensor",
        interval="5m"
    )
    print(f"对比数据点: {len(compare)} 个")
