# ============================================================
# 文件说明: parser_roller_kiln.py - 辊道窑数据块解析器
# ============================================================
# 方法列表:
# 1. __init__()              - 初始化解析器
# 2. load_config()           - 加载配置
# 3. parse_module()          - 解析单个模块数据
# 4. parse_all()             - 解析辊道窑数据
# 5. get_device_info()       - 获取设备信息
# ============================================================

import struct
import yaml
from typing import Dict, List, Any
from pathlib import Path
from datetime import datetime


class RollerKilnParser:
    """辊道窑数据块解析器
    
    负责解析辊道窑设备数据:
    - 6个分区电表 (zone1_meter ~ zone6_meter)
    - 6个温度传感器 (对应6个温区)
    
    注意: 没有主电表，只有6个分区电表
    """
    
    # 项目根目录 (ceramic-workshop-backend/)
    PROJECT_ROOT = Path(__file__).parent.parent.parent
    
    # ------------------------------------------------------------
    # 1. __init__() - 初始化解析器
    # ------------------------------------------------------------
    def __init__(self, 
                 db_config_path: str = None,
                 module_config_path: str = None):
        """初始化解析器
        
        Args:
            db_config_path: DB9配置文件路径
            module_config_path: 基础模块配置文件路径
        """
        # 使用绝对路径，避免工作目录问题
        self.db_config_path = Path(db_config_path) if db_config_path else self.PROJECT_ROOT / "configs" / "config_roller_kiln_9.yaml"
        self.module_config_path = Path(module_config_path) if module_config_path else self.PROJECT_ROOT / "configs" / "plc_modules.yaml"
        
        self.db_config = None
        self.base_modules = {}   # 基础模块定义
        self.device_config = None  # 辊道窑设备配置
        
        self.load_config()
    
    # ------------------------------------------------------------
    # 2. load_config() - 加载配置
    # ------------------------------------------------------------
    def load_config(self):
        """加载DB9配置和基础模块配置"""
        # 加载基础模块配置
        with open(self.module_config_path, 'r', encoding='utf-8') as f:
            module_config = yaml.safe_load(f)
            for module in module_config.get('modules', []):
                self.base_modules[module['name']] = module
        
        # 加载DB9辊道窑配置
        with open(self.db_config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            self.db_config = config.get('db_config', {})
            self.device_config = config.get('roller_kiln', {})
        
        print(f"[OK] DB9解析器初始化完成: 设备={self.device_config['device_name']}, "
              f"DB{self.db_config['db_number']}, 总大小{self.db_config['total_size']}字节, "
              f"6个分区电表")
    
    # ------------------------------------------------------------
    # 3. parse_module() - 解析单个模块数据
    # ------------------------------------------------------------
    def parse_module(self, module_config: Dict, data: bytes, offset: int) -> Dict[str, Any]:
        """解析单个模块数据
        
        Args:
            module_config: 模块配置
            data: DB9的完整字节数据
            offset: 模块在DB9中的起始偏移量
            
        Returns:
            解析后的模块数据
        """
        module_type = module_config['module_type']
        module_size = module_config['size']
        
        # 获取基础模块定义
        if module_type not in self.base_modules:
            raise ValueError(f"未找到基础模块定义: {module_type}")
        
        base_module = self.base_modules[module_type]
        
        # 切出模块数据
        module_data = data[offset:offset + module_size]
        
        # 解析所有字段
        parsed_fields = {}
        for field in base_module['fields']:
            field_offset = field['offset']
            data_type = field['data_type']
            field_name = field['name']
            
            try:
                # 解析字段值
                if data_type == 'Word':
                    value = struct.unpack('>H', module_data[field_offset:field_offset+2])[0]
                elif data_type == 'DWord':
                    value = struct.unpack('>I', module_data[field_offset:field_offset+4])[0]
                elif data_type == 'Int':
                    value = struct.unpack('>h', module_data[field_offset:field_offset+2])[0]
                elif data_type == 'DInt':
                    value = struct.unpack('>i', module_data[field_offset:field_offset+4])[0]
                elif data_type == 'Real':
                    value = struct.unpack('>f', module_data[field_offset:field_offset+4])[0]
                else:
                    value = 0.0
                
                # 应用缩放
                scale = field.get('scale', 1.0)
                if isinstance(value, (int, float)):
                    value = value * scale
                
                parsed_fields[field_name] = {
                    'value': value,
                    'display_name': field.get('display_name', field_name),
                    'unit': field.get('unit', '')
                }
            
            except Exception as e:
                print(f"[WARN]  解析字段失败 {module_type}.{field_name} @ offset {offset + field_offset}: {e}")
                parsed_fields[field_name] = {
                    'value': 0.0,
                    'display_name': field.get('display_name', field_name),
                    'unit': field.get('unit', '')
                }
        
        return {
            'module_type': module_type,
            'tag': module_config['tag'],
            'description': module_config.get('description', ''),
            'fields': parsed_fields
        }
    
    # ------------------------------------------------------------
    # 4. parse_all() - 解析DB9辊道窑数据
    # ------------------------------------------------------------
    def parse_all(self, db9_data: bytes) -> List[Dict[str, Any]]:
        """解析DB9辊道窑数据
        
        Args:
            db9_data: DB9的完整字节数据
            
        Returns:
            设备列表 (与DB8/DB10格式统一，便于统一处理)
        """
        device_result = {
            'device_id': self.device_config['device_id'],
            'device_name': self.device_config['device_name'],
            'device_type': self.device_config['device_type'],
            'category': 'roller_kiln',
            'timestamp': datetime.now().isoformat(),
            'modules': {}
        }
        
        try:
            # 解析6个分区电表 (zone1_meter ~ zone6_meter)
            for meter_config in self.device_config['electricity_meters']:
                offset = meter_config['offset']
                tag = meter_config['tag']
                parsed = self.parse_module(meter_config, db9_data, offset)
                device_result['modules'][tag] = parsed
            
            # 解析6个温度传感器
            for temp_config in self.device_config['temperature_sensors']:
                offset = temp_config['offset']
                tag = temp_config['tag']
                parsed = self.parse_module(temp_config, db9_data, offset)
                device_result['modules'][tag] = parsed
        
        except Exception as e:
            print(f"[WARN]  解析辊道窑数据失败: {e}")
        
        # 返回列表格式，与DB8/DB10统一
        return [device_result]
    
    # ------------------------------------------------------------
    # 5. get_device_info() - 获取设备信息
    # ------------------------------------------------------------
    def get_device_info(self) -> Dict[str, str]:
        """获取设备信息
        
        Returns:
            设备基本信息
        """
        return {
            'device_id': self.device_config['device_id'],
            'device_name': self.device_config['device_name'],
            'device_type': self.device_config['device_type'],
            'db_number': self.db_config['db_number'],
            'total_size': self.db_config['total_size'],
            'meter_count': len(self.device_config['electricity_meters']),
            'temp_count': len(self.device_config['temperature_sensors'])
        }


# ============================================================
# 使用示例
# ============================================================
if __name__ == "__main__":
    # 测试解析器
    parser = RollerKilnParser()
    
    # 打印设备信息
    info = parser.get_device_info()
    print("\n设备信息:")
    print(f"  - 设备名称: {info['device_name']}")
    print(f"  - 设备ID: {info['device_id']}")
    print(f"  - DB块: DB{info['db_number']}, 大小{info['total_size']}字节")
    print(f"  - 电表数量: {info['meter_count']}个")
    print(f"  - 温度传感器: {info['temp_count']}个")
    
    # 模拟DB9数据 (348字节全0)
    test_data = bytes(348)
    
    # 解析辊道窑数据 (返回列表)
    results = parser.parse_all(test_data)
    device = results[0]
    
    print(f"\n解析完成: {device['device_name']}")
    print(f"\n模块数据 ({len(device['modules'])}个):")
    for tag, module in list(device['modules'].items())[:4]:
        print(f"  {tag} ({module['module_type']}):")
        for field_name, field_info in list(module['fields'].items())[:2]:
            print(f"    - {field_info['display_name']}: {field_info['value']} {field_info['unit']}")
