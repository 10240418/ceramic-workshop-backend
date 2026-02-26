# ============================================================
# 文件说明: roller_kiln_aggregator.py - 辊道窑数据聚合服务
# ============================================================
# 功能:
# 1. 从6个分区电表数据计算总值（总功率、总能耗、总电流）
# 2. 将总值作为虚拟设备 "roller_kiln_total" 存入数据库
# 3. 供API和导出服务使用
# ============================================================

from datetime import datetime
from typing import Dict, Any, Optional, List
from app.core.influxdb import build_point

class RollerKilnAggregator:
    """辊道窑数据聚合器
    
    负责计算6个分区电表的总值，并生成虚拟设备数据点
    """
    
    def __init__(self):
        self.zone_tags = [
            "zone1_meter",
            "zone2_meter", 
            "zone3_meter",
            "zone4_meter",
            "zone5_meter",
            "zone6_meter"
        ]
    
    def aggregate_zones(
        self, 
        device_data: Dict[str, Any],
        timestamp: datetime
    ) -> Optional[Any]:
        """聚合6个分区电表数据，生成总表数据点
        
        Args:
            device_data: 辊道窑设备数据（包含6个分区电表）
            timestamp: 时间戳
            
        Returns:
            InfluxDB Point对象，如果数据不完整则返回None
        """
        if device_data.get('device_id') != 'roller_kiln_1':
            return None
        
        modules = device_data.get('modules', {})
        
        # 初始化累加器
        total_power = 0.0       # 总功率 (kW)
        total_energy = 0.0      # 总能耗 (kWh)
        total_current_a = 0.0   # A相总电流 (A)
        total_current_b = 0.0   # B相总电流 (A)
        total_current_c = 0.0   # C相总电流 (A)
        total_voltage = 0.0     # 平均电压 (V)
        
        valid_zones = 0
        
        # 遍历6个分区电表
        for zone_tag in self.zone_tags:
            zone_module = modules.get(zone_tag)
            if not zone_module:
                continue
            
            fields = zone_module.get('fields', {})
            
            # [FIX] 修复：检查 fields 是否是嵌套字典（包含 'value' 键）
            # 如果是，提取 value；否则直接使用
            def get_field_value(field_name: str, default: float = 0.0) -> float:
                field_data = fields.get(field_name, default)
                if isinstance(field_data, dict) and 'value' in field_data:
                    return float(field_data['value'])
                return float(field_data) if field_data is not None else default
            
            # 累加功率和能耗
            total_power += get_field_value('Pt', 0.0)
            total_energy += get_field_value('ImpEp', 0.0)
            
            # 累加三相电流
            total_current_a += get_field_value('I_0', 0.0)
            total_current_b += get_field_value('I_1', 0.0)
            total_current_c += get_field_value('I_2', 0.0)
            
            # 累加电压（用于计算平均值）
            total_voltage += get_field_value('Ua_0', 0.0)
            
            valid_zones += 1
        
        # 如果没有有效分区数据，返回None
        if valid_zones == 0:
            return None
        
        # 计算平均电压
        avg_voltage = total_voltage / valid_zones if valid_zones > 0 else 0.0
        
        # 构建总表数据点
        point = build_point(
            measurement="sensor_data",
            tags={
                "device_id": "roller_kiln_total",
                "device_type": "roller_kiln_total",
                "module_type": "ElectricityMeter",
                "module_tag": "total_meter",
                "db_number": "9"
            },
            fields={
                "Pt": round(total_power, 2),           # 总功率
                "ImpEp": round(total_energy, 2),       # 总能耗
                "Ua_0": round(avg_voltage, 2),         # 平均电压
                "I_0": round(total_current_a, 2),      # A相总电流
                "I_1": round(total_current_b, 2),      # B相总电流
                "I_2": round(total_current_c, 2),      # C相总电流
            },
            timestamp=timestamp
        )
        
        return point
    
    def aggregate_zones_for_cache(
        self,
        device_data: Dict[str, Any],
        timestamp: datetime
    ) -> Optional[Dict[str, Any]]:
        """聚合6个分区电表数据，生成总表缓存数据
        
        用于更新内存缓存，供API直接读取
        
        Args:
            device_data: 辊道窑设备数据
            timestamp: 时间戳
            
        Returns:
            总表设备数据字典
        """
        if device_data.get('device_id') != 'roller_kiln_1':
            return None
        
        modules = device_data.get('modules', {})
        
        # 初始化累加器
        total_power = 0.0
        total_energy = 0.0
        total_current_a = 0.0
        total_current_b = 0.0
        total_current_c = 0.0
        total_voltage = 0.0
        
        valid_zones = 0
        
        # 遍历6个分区电表
        for zone_tag in self.zone_tags:
            zone_module = modules.get(zone_tag)
            if not zone_module:
                continue
            
            fields = zone_module.get('fields', {})
            
            # [FIX] 修复：检查 fields 是否是嵌套字典（包含 'value' 键）
            def get_field_value(field_name: str, default: float = 0.0) -> float:
                field_data = fields.get(field_name, default)
                if isinstance(field_data, dict) and 'value' in field_data:
                    return float(field_data['value'])
                return float(field_data) if field_data is not None else default
            
            total_power += get_field_value('Pt', 0.0)
            total_energy += get_field_value('ImpEp', 0.0)
            total_current_a += get_field_value('I_0', 0.0)
            total_current_b += get_field_value('I_1', 0.0)
            total_current_c += get_field_value('I_2', 0.0)
            total_voltage += get_field_value('Ua_0', 0.0)
            
            valid_zones += 1
        
        if valid_zones == 0:
            return None
        
        avg_voltage = total_voltage / valid_zones if valid_zones > 0 else 0.0
        
        # 构建总表缓存数据
        return {
            "device_id": "roller_kiln_total",
            "device_type": "roller_kiln_total",
            "db_number": "9",
            "timestamp": timestamp.isoformat(),
            "modules": {
                "total_meter": {
                    "module_type": "ElectricityMeter",
                    "fields": {
                        "Pt": round(total_power, 2),
                        "ImpEp": round(total_energy, 2),
                        "Ua_0": round(avg_voltage, 2),
                        "I_0": round(total_current_a, 2),
                        "I_1": round(total_current_b, 2),
                        "I_2": round(total_current_c, 2),
                    }
                }
            }
        }


# 单例实例
_aggregator_instance: Optional[RollerKilnAggregator] = None


def get_aggregator() -> RollerKilnAggregator:
    """获取辊道窑聚合器单例"""
    global _aggregator_instance
    if _aggregator_instance is None:
        _aggregator_instance = RollerKilnAggregator()
    return _aggregator_instance

