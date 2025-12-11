#!/usr/bin/env python3
# ============================================================
# 文件说明: plc_config_manager.py - PLC 动态配置管理器
# ============================================================
# 方法列表:
# 1. load_data_points()        - 加载数据点配置
# 2. get_device_points()       - 获取指定设备的数据点
# 3. validate_config()         - 验证配置有效性
# 4. generate_schema()         - 自动生成 InfluxDB Schema
# 5. add_data_point()          - 动态添加数据点
# 6. update_data_point()       - 更新数据点配置
# 7. reload_config()           - 热重载配置
# ============================================================

import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum


class PLCDataType(str, Enum):
    """PLC 数据类型枚举"""
    BOOL = "BOOL"
    BYTE = "BYTE"
    WORD = "WORD"
    DWORD = "DWORD"
    INT = "INT"
    DINT = "DINT"
    REAL = "REAL"


@dataclass
class DataPoint:
    """数据点定义"""
    name: str                    # 中文名称
    point_id: str                # 唯一标识
    db_offset: int               # DB块字节偏移
    data_type: PLCDataType       # 数据类型
    scale: float                 # 缩放因子
    unit: str                    # 单位
    measurement: str             # InfluxDB Measurement
    field_name: str              # InfluxDB Field
    tags: Dict[str, str]         # InfluxDB Tags
    enabled: bool                # 是否启用
    bit_offset: Optional[int] = None  # BOOL类型的位偏移
    
    def get_byte_size(self) -> int:
        """获取数据类型的字节大小"""
        size_map = {
            PLCDataType.BOOL: 1,
            PLCDataType.BYTE: 1,
            PLCDataType.WORD: 2,
            PLCDataType.DWORD: 4,
            PLCDataType.INT: 2,
            PLCDataType.DINT: 4,
            PLCDataType.REAL: 4,
        }
        return size_map.get(self.data_type, 0)


@dataclass
class DeviceConfig:
    """设备配置"""
    device_type: str             # 设备类型
    measurement_prefix: str      # Measurement前缀
    db_number: int               # DB块编号
    data_points: List[DataPoint] # 数据点列表


class PLCConfigManager:
    """PLC 配置管理器
    
    功能:
    - 加载和管理 PLC 数据点配置
    - 动态添加/修改数据点
    - 自动生成 InfluxDB Schema
    - 配置验证
    """
    
    def __init__(self, config_dir: str = "configs"):
        """初始化配置管理器
        
        Args:
            config_dir: 配置文件目录
        """
        self.config_dir = Path(config_dir)
        self.data_points_file = self.config_dir / "plc_data_points.yaml"
        self.devices_file = self.config_dir / "devices.yaml"
        
        self.config: Dict[str, DeviceConfig] = {}
        self._load_config()
    
    # ------------------------------------------------------------
    # 1. load_config() - 加载配置文件
    # ------------------------------------------------------------
    def _load_config(self):
        """加载配置文件"""
        if not self.data_points_file.exists():
            raise FileNotFoundError(f"配置文件不存在: {self.data_points_file}")
        
        with open(self.data_points_file, 'r', encoding='utf-8') as f:
            raw_config = yaml.safe_load(f)
        
        # 兼容空配置文件（使用新的模块化配置系统）
        if raw_config is None or not isinstance(raw_config, dict):
            print("⚠️  使用新的模块化配置系统 (plc_modules.yaml)")
            return
        
        # 解析每个设备的配置
        for device_key, device_data in raw_config.items():
            if device_key.startswith('#') or not isinstance(device_data, dict):
                continue
            
            # 解析数据点
            data_points = []
            for point_data in device_data.get('data_points', []):
                try:
                    data_point = DataPoint(
                        name=point_data['name'],
                        point_id=point_data['point_id'],
                        db_offset=point_data['db_offset'],
                        data_type=PLCDataType(point_data['data_type']),
                        scale=point_data.get('scale', 1.0),
                        unit=point_data.get('unit', ''),
                        measurement=point_data['measurement'],
                        field_name=point_data['field_name'],
                        tags=point_data.get('tags', {}),
                        enabled=point_data.get('enabled', True),
                        bit_offset=point_data.get('bit_offset')
                    )
                    data_points.append(data_point)
                except Exception as e:
                    print(f"⚠️  解析数据点失败: {point_data.get('name', 'unknown')} - {e}")
            
            # 创建设备配置
            self.config[device_key] = DeviceConfig(
                device_type=device_data['device_type'],
                measurement_prefix=device_data['measurement_prefix'],
                db_number=device_data['db_number'],
                data_points=data_points
            )
    
    # ------------------------------------------------------------
    # 2. get_device_points() - 获取设备数据点
    # ------------------------------------------------------------
    def get_device_points(
        self, 
        device_type: str, 
        enabled_only: bool = True
    ) -> List[DataPoint]:
        """获取指定设备的数据点列表
        
        Args:
            device_type: 设备类型 (roller_kiln, rotary_kiln, scr)
            enabled_only: 是否只返回启用的数据点
        
        Returns:
            数据点列表
        """
        if device_type not in self.config:
            return []
        
        points = self.config[device_type].data_points
        
        if enabled_only:
            points = [p for p in points if p.enabled]
        
        return points
    
    # ------------------------------------------------------------
    # 3. validate_config() - 验证配置
    # ------------------------------------------------------------
    def validate_config(self) -> Dict[str, List[str]]:
        """验证配置有效性
        
        Returns:
            验证结果字典 {device_type: [errors]}
        """
        errors = {}
        
        for device_key, device_config in self.config.items():
            device_errors = []
            
            # 检查数据点ID唯一性
            point_ids = [p.point_id for p in device_config.data_points]
            if len(point_ids) != len(set(point_ids)):
                device_errors.append("存在重复的 point_id")
            
            # 检查偏移量合理性
            for point in device_config.data_points:
                if point.db_offset < 0 or point.db_offset > 65535:
                    device_errors.append(
                        f"数据点 {point.name} 的偏移量超出范围: {point.db_offset}"
                    )
                
                # BOOL类型必须有bit_offset
                if point.data_type == PLCDataType.BOOL and point.bit_offset is None:
                    device_errors.append(
                        f"数据点 {point.name} 是BOOL类型但未指定bit_offset"
                    )
            
            if device_errors:
                errors[device_key] = device_errors
        
        return errors
    
    # ------------------------------------------------------------
    # 4. generate_schema() - 生成 InfluxDB Schema
    # ------------------------------------------------------------
    def generate_schema(self) -> Dict[str, Any]:
        """自动生成 InfluxDB Schema 定义
        
        Returns:
            Schema 定义字典
        """
        measurements = {}
        
        for device_key, device_config in self.config.items():
            for point in device_config.data_points:
                if not point.enabled:
                    continue
                
                measurement_name = point.measurement
                
                if measurement_name not in measurements:
                    measurements[measurement_name] = {
                        'name': measurement_name,
                        'tags': set(),
                        'fields': {}
                    }
                
                # 收集 tags
                for tag_key in point.tags.keys():
                    measurements[measurement_name]['tags'].add(tag_key)
                
                # 收集 fields
                if point.field_name not in measurements[measurement_name]['fields']:
                    measurements[measurement_name]['fields'][point.field_name] = {
                        'type': self._map_plc_type_to_influx(point.data_type),
                        'unit': point.unit,
                        'description': point.name
                    }
        
        # 转换 set 为 list
        for m in measurements.values():
            m['tags'] = list(m['tags'])
        
        return measurements
    
    def _map_plc_type_to_influx(self, plc_type: PLCDataType) -> str:
        """映射 PLC 数据类型到 InfluxDB 数据类型"""
        type_map = {
            PLCDataType.BOOL: 'integer',
            PLCDataType.BYTE: 'integer',
            PLCDataType.WORD: 'integer',
            PLCDataType.DWORD: 'integer',
            PLCDataType.INT: 'integer',
            PLCDataType.DINT: 'integer',
            PLCDataType.REAL: 'float',
        }
        return type_map.get(plc_type, 'float')
    
    # ------------------------------------------------------------
    # 5. add_data_point() - 添加数据点
    # ------------------------------------------------------------
    def add_data_point(
        self, 
        device_type: str, 
        point_config: Dict[str, Any]
    ) -> bool:
        """动态添加数据点
        
        Args:
            device_type: 设备类型
            point_config: 数据点配置字典
        
        Returns:
            是否成功
        """
        if device_type not in self.config:
            print(f"❌ 设备类型不存在: {device_type}")
            return False
        
        try:
            # 创建数据点对象
            data_point = DataPoint(
                name=point_config['name'],
                point_id=point_config['point_id'],
                db_offset=point_config['db_offset'],
                data_type=PLCDataType(point_config['data_type']),
                scale=point_config.get('scale', 1.0),
                unit=point_config.get('unit', ''),
                measurement=point_config['measurement'],
                field_name=point_config['field_name'],
                tags=point_config.get('tags', {}),
                enabled=point_config.get('enabled', True),
                bit_offset=point_config.get('bit_offset')
            )
            
            # 添加到配置
            self.config[device_type].data_points.append(data_point)
            
            # 保存到文件
            self._save_config()
            
            print(f"✅ 数据点添加成功: {data_point.name}")
            return True
            
        except Exception as e:
            print(f"❌ 添加数据点失败: {e}")
            return False
    
    # ------------------------------------------------------------
    # 6. update_data_point() - 更新数据点
    # ------------------------------------------------------------
    def update_data_point(
        self, 
        device_type: str, 
        point_id: str, 
        updates: Dict[str, Any]
    ) -> bool:
        """更新数据点配置
        
        Args:
            device_type: 设备类型
            point_id: 数据点ID
            updates: 更新的字段
        
        Returns:
            是否成功
        """
        if device_type not in self.config:
            print(f"❌ 设备类型不存在: {device_type}")
            return False
        
        # 查找数据点
        point = None
        for p in self.config[device_type].data_points:
            if p.point_id == point_id:
                point = p
                break
        
        if not point:
            print(f"❌ 数据点不存在: {point_id}")
            return False
        
        # 更新字段
        for key, value in updates.items():
            if hasattr(point, key):
                if key == 'data_type':
                    value = PLCDataType(value)
                setattr(point, key, value)
        
        # 保存到文件
        self._save_config()
        
        print(f"✅ 数据点更新成功: {point.name}")
        return True
    
    # ------------------------------------------------------------
    # 7. reload_config() - 热重载配置
    # ------------------------------------------------------------
    def reload_config(self):
        """重新加载配置文件（热重载）"""
        print("🔄 重新加载配置...")
        self.config.clear()
        self._load_config()
        print("✅ 配置重载完成")
    
    def _save_config(self):
        """保存配置到文件"""
        raw_config = {}
        
        for device_key, device_config in self.config.items():
            raw_config[device_key] = {
                'device_type': device_config.device_type,
                'measurement_prefix': device_config.measurement_prefix,
                'db_number': device_config.db_number,
                'data_points': []
            }
            
            for point in device_config.data_points:
                point_dict = {
                    'name': point.name,
                    'point_id': point.point_id,
                    'db_offset': point.db_offset,
                    'data_type': point.data_type.value,
                    'scale': point.scale,
                    'unit': point.unit,
                    'measurement': point.measurement,
                    'field_name': point.field_name,
                    'tags': point.tags,
                    'enabled': point.enabled
                }
                
                if point.bit_offset is not None:
                    point_dict['bit_offset'] = point.bit_offset
                
                raw_config[device_key]['data_points'].append(point_dict)
        
        with open(self.data_points_file, 'w', encoding='utf-8') as f:
            yaml.dump(raw_config, f, allow_unicode=True, sort_keys=False)
    
    # ------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------
    def get_summary(self) -> Dict[str, Any]:
        """获取配置摘要"""
        summary = {}
        
        for device_key, device_config in self.config.items():
            enabled_count = sum(1 for p in device_config.data_points if p.enabled)
            total_count = len(device_config.data_points)
            
            summary[device_key] = {
                'device_type': device_config.device_type,
                'db_number': device_config.db_number,
                'total_points': total_count,
                'enabled_points': enabled_count,
                'disabled_points': total_count - enabled_count
            }
        
        return summary
    
    def list_measurements(self) -> List[str]:
        """列出所有 Measurement 名称"""
        measurements = set()
        
        for device_config in self.config.values():
            for point in device_config.data_points:
                if point.enabled:
                    measurements.add(point.measurement)
        
        return sorted(list(measurements))


# ============================================================
# 命令行工具
# ============================================================
if __name__ == "__main__":
    import sys
    from tabulate import tabulate
    
    manager = PLCConfigManager()
    
    if len(sys.argv) < 2:
        print("""
使用方法:
    python app/core/plc_config_manager.py summary      # 配置摘要
    python app/core/plc_config_manager.py validate     # 验证配置
    python app/core/plc_config_manager.py schema       # 生成Schema
    python app/core/plc_config_manager.py list <设备>  # 列出数据点
        """)
        sys.exit(0)
    
    command = sys.argv[1]
    
    if command == "summary":
        print("\n📊 配置摘要\n")
        summary = manager.get_summary()
        data = [[k, v['device_type'], v['db_number'], 
                v['enabled_points'], v['total_points']] 
                for k, v in summary.items()]
        print(tabulate(data, headers=[
            "设备", "类型", "DB块", "启用点数", "总点数"
        ], tablefmt="grid"))
    
    elif command == "validate":
        print("\n🔍 验证配置\n")
        errors = manager.validate_config()
        if not errors:
            print("✅ 配置验证通过")
        else:
            for device, error_list in errors.items():
                print(f"\n❌ {device}:")
                for err in error_list:
                    print(f"  - {err}")
    
    elif command == "schema":
        print("\n📋 InfluxDB Schema\n")
        schema = manager.generate_schema()
        for name, info in schema.items():
            print(f"\n📊 {name}")
            print(f"  Tags: {', '.join(info['tags']) if info['tags'] else '无'}")
            print(f"  Fields:")
            for field, field_info in info['fields'].items():
                print(f"    - {field}: {field_info['type']} ({field_info['unit']})")
    
    elif command == "list":
        if len(sys.argv) < 3:
            print("❌ 请指定设备类型")
            sys.exit(1)
        
        device_type = sys.argv[2]
        points = manager.get_device_points(device_type)
        
        if not points:
            print(f"❌ 设备类型不存在或无数据点: {device_type}")
            sys.exit(1)
        
        print(f"\n📋 {device_type} 数据点列表\n")
        data = [[p.name, p.point_id, p.db_offset, p.data_type.value, 
                p.scale, p.unit, p.measurement] 
                for p in points]
        print(tabulate(data, headers=[
            "名称", "ID", "偏移", "类型", "缩放", "单位", "Measurement"
        ], tablefmt="grid"))
