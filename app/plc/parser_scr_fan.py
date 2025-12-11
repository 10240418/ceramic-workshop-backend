# ============================================================
# 文件说明: parser_scr_fan.py - SCR设备和风机数据块解析器
# ============================================================
# 方法列表:
# 1. __init__()              - 初始化解析器
# 2. load_config()           - 加载配置
# 3. parse_module()          - 解析单个模块数据
# 4. parse_all()             - 解析所有设备数据
# 5. get_device_list()       - 获取设备列表
# ============================================================

import struct
import yaml
from typing import Dict, List, Any
from pathlib import Path
from datetime import datetime


class SCRFanParser:
    """SCR设备和风机数据块解析器
    
    负责解析设备数据:
    - SCR设备 (2个): 电表(氨水泵) + 燃气表
    - 风机 (2个): 电表
    """
    
    # ------------------------------------------------------------
    # 1. __init__() - 初始化解析器
    # ------------------------------------------------------------
    def __init__(self, 
                 db_config_path: str = "configs/config_scr_fans.yaml",
                 module_config_path: str = "configs/plc_modules.yaml"):
        """初始化解析器
        
        Args:
            db_config_path: DB8配置文件路径
            module_config_path: 基础模块配置文件路径
        """
        self.db_config_path = Path(db_config_path)
        self.module_config_path = Path(module_config_path)
        
        self.db_config = None
        self.base_modules = {}  # 基础模块定义
        self.devices = []       # 所有设备列表
        
        self.load_config()
    
    # ------------------------------------------------------------
    # 2. load_config() - 加载配置
    # ------------------------------------------------------------
    def load_config(self):
        """加载DB8配置和基础模块配置"""
        # 加载基础模块配置
        with open(self.module_config_path, 'r', encoding='utf-8') as f:
            module_config = yaml.safe_load(f)
            for module in module_config.get('modules', []):
                self.base_modules[module['name']] = module
        
        # 加载DB8设备配置
        with open(self.db_config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            self.db_config = config.get('db_config', {})
            
            # 收集SCR设备
            for device in config.get('scr_devices', []):
                device['category'] = 'scr'
                self.devices.append(device)
            
            # 收集风机
            for device in config.get('fans', []):
                device['category'] = 'fan'
                self.devices.append(device)
        
        print(f"✅ DB8解析器初始化完成: {len(self.devices)}个设备, "
              f"DB{self.db_config['db_number']}, 总大小{self.db_config['total_size']}字节")
    
    # ------------------------------------------------------------
    # 3. parse_module() - 解析单个模块数据
    # ------------------------------------------------------------
    def parse_module(self, module_config: Dict, data: bytes, offset: int) -> Dict[str, Any]:
        """解析单个模块数据
        
        Args:
            module_config: 模块配置
            data: DB8的完整字节数据
            offset: 模块在DB8中的起始偏移量
            
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
                print(f"⚠️  解析字段失败 {module_type}.{field_name} @ offset {offset + field_offset}: {e}")
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
    # 4. parse_all() - 解析DB8所有设备数据
    # ------------------------------------------------------------
    def parse_all(self, db8_data: bytes) -> List[Dict[str, Any]]:
        """解析DB8所有设备数据
        
        Args:
            db8_data: DB8的完整字节数据
            
        Returns:
            所有设备的解析结果列表
        """
        results = []
        
        for device in self.devices:
            try:
                device_result = {
                    'device_id': device['device_id'],
                    'device_name': device['device_name'],
                    'device_type': device['device_type'],
                    'category': device['category'],
                    'timestamp': datetime.now().isoformat(),
                    'modules': {}
                }
                
                # 解析设备的所有模块
                for module_config in device['modules']:
                    module_offset = module_config['offset']
                    module_tag = module_config['tag']
                    
                    parsed_module = self.parse_module(module_config, db8_data, module_offset)
                    device_result['modules'][module_tag] = parsed_module
                
                results.append(device_result)
            
            except Exception as e:
                print(f"⚠️  解析设备失败 {device['device_id']}: {e}")
        
        return results
    
    # ------------------------------------------------------------
    # 5. get_device_list() - 获取设备列表
    # ------------------------------------------------------------
    def get_device_list(self) -> List[Dict[str, str]]:
        """获取设备列表
        
        Returns:
            设备基本信息列表
        """
        return [
            {
                'device_id': dev['device_id'],
                'device_name': dev['device_name'],
                'device_type': dev['device_type'],
                'category': dev['category']
            }
            for dev in self.devices
        ]


# ============================================================
# 使用示例
# ============================================================
if __name__ == "__main__":
    # 测试解析器
    parser = SCRFanParser()
    
    # 打印设备列表
    print("\n设备列表:")
    for dev in parser.get_device_list():
        print(f"  - {dev['device_name']} ({dev['device_id']}): {dev['category']}")
    
    # 模拟DB8数据 (176字节全0)
    test_data = bytes(176)
    
    # 解析所有设备
    results = parser.parse_all(test_data)
    
    print(f"\n解析完成: {len(results)}个设备")
    for result in results:
        print(f"\n{result['device_name']} ({result['category']}):")
        for tag, module in result['modules'].items():
            print(f"  {tag} ({module['description']}):")
            for field_name, field_info in list(module['fields'].items())[:3]:
                print(f"    - {field_info['display_name']}: {field_info['value']} {field_info['unit']}")
