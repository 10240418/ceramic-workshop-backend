# ============================================================
# 文件说明: module_parser.py - 模块化数据解析器
# ============================================================
# 方法列表:
# 1. __init__()              - 初始化解析器
# 2. load_module_configs()   - 加载模块配置
# 3. parse_field()           - 解析单个字段
# 4. parse_module()          - 解析模块数据
# 5. parse_device_data()     - 解析设备所有模块数据
# ============================================================

import struct
import yaml
from typing import Dict, List, Any
from pathlib import Path
from datetime import datetime


class ModuleParser:
    """模块化数据解析器"""
    
    # ------------------------------------------------------------
    # 1. __init__() - 初始化解析器
    # ------------------------------------------------------------
    def __init__(self, config_path: str = "configs/plc_modules.yaml"):
        """初始化解析器"""
        self.config_path = Path(config_path)
        self.modules = {}
        self.load_module_configs()
    
    # ------------------------------------------------------------
    # 2. load_module_configs() - 加载模块配置
    # ------------------------------------------------------------
    def load_module_configs(self):
        """加载模块配置"""
        with open(self.config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            
        # 将模块列表转换为字典，方便查找
        for module in config.get('modules', []):
            self.modules[module['name']] = module
            
        print(f"[OK] 加载了 {len(self.modules)} 个模块配置")
    
    # ------------------------------------------------------------
    # 3. parse_field() - 解析单个字段 (支持递归 Struct)
    # ------------------------------------------------------------
    def parse_field(self, data: bytes, field: Dict[str, Any], base_offset: int = 0) -> Any:
        """解析单个字段
        
        Args:
            data: 模块的原始字节数据 (整个模块的数据)
            field: 字段配置字典
            base_offset: 当前层级的起始偏移量 (用于递归)
            
        Returns:
            解析后的数值或字典(Struct)
        """
        # 计算绝对偏移量：模块起始 + 父级偏移 + 当前字段偏移
        # 注意：这里的 data 已经是模块切片后的数据，所以只需要关注相对偏移
        # field['offset'] 是相对父级的偏移
        current_offset = base_offset + field['offset']
        data_type = field['data_type']
        scale = field.get('scale', 1.0)
        
        try:
            # 处理 Struct 类型 (递归解析)
            if data_type == 'Struct':
                children = field.get('children', [])
                struct_result = {}
                for child in children:
                    # 递归调用，基准偏移量变为当前 Struct 的起始位置
                    child_value = self.parse_field(data, child, base_offset=current_offset)
                    struct_result[child['name']] = child_value
                return struct_result

            # 处理基础数据类型
            if data_type == 'Word':
                # 16位无符号整数 (Big Endian)
                raw_value = struct.unpack('>H', data[current_offset:current_offset+2])[0]
            elif data_type == 'DWord':
                # 32位无符号整数 (Big Endian)
                raw_value = struct.unpack('>I', data[current_offset:current_offset+4])[0]
            elif data_type == 'Int':
                # 16位有符号整数 (Big Endian)
                raw_value = struct.unpack('>h', data[current_offset:current_offset+2])[0]
            elif data_type == 'DInt':
                # 32位有符号整数 (Big Endian)
                raw_value = struct.unpack('>i', data[current_offset:current_offset+4])[0]
            elif data_type == 'Real':
                # 32位浮点数 (Big Endian)
                raw_value = struct.unpack('>f', data[current_offset:current_offset+4])[0]
            elif data_type == 'Bool':
                # 布尔值
                # bit_offset 是字段定义的位偏移
                bit_offset = field.get('bit_offset', 0)
                byte_val = data[current_offset]
                raw_value = bool(byte_val & (1 << bit_offset))
            else:
                # 暂不支持的类型，返回 None 或 0
                return 0.0
            
            # 应用缩放因子 (仅对数值类型有效)
            if isinstance(raw_value, (int, float)):
                return raw_value * scale
            return raw_value
            
        except Exception as e:
            print(f"[WARN]  解析字段 {field.get('name')} 失败 (Offset: {current_offset}, Type: {data_type}): {e}")
            return 0.0
    
    # ------------------------------------------------------------
    # 4. parse_module() - 解析模块数据
    # ------------------------------------------------------------
    def parse_module(self, module_name: str, data: bytes) -> Dict[str, Any]:
        """解析模块数据
        
        Args:
            module_name: 模块名称
            data: 整个DB块的原始数据 (注意：这里传入的是读取到的原始二进制数据)
            
        Returns:
            解析后的模块数据字典
        """
        if module_name not in self.modules:
            raise ValueError(f"未找到模块配置: {module_name}")
        
        module_config = self.modules[module_name]
        # 注意：如果 PLCService 已经根据 start_offset 切割了数据，这里就不需要再切了
        # 但通常 PLCService 读取的是一大块数据，所以这里需要根据模块配置切片
        # 假设传入的 data 就是这个模块对应的数据片段（由 PLCService 处理切割）
        # 或者假设传入的是整个 DB 块，需要自己切。
        # 根据之前的代码逻辑，PLCService 读取的是 max(total_size) 的一大块。
        # 为了安全起见，我们假设 data 是从 start_offset 开始的正确数据片段，或者我们在 PLCService 里处理好。
        # 这里我们保持简单：假设 data 就是该模块的数据内容 (长度 = total_size)
        
        # 解析所有字段
        parsed_data = {
            'module_name': module_name,
            'description': module_config.get('description', ''),
            'fields': {}
        }
        
        for field in module_config['fields']:
            # 从 0 开始解析，因为 data 已经是模块的数据了
            field_value = self.parse_field(data, field, base_offset=0)
            
            # 构造返回结构
            field_info = {
                'value': field_value,
                'display_name': field.get('display_name', field['name']),
                'unit': field.get('unit', '')
            }
            parsed_data['fields'][field['name']] = field_info
        
        return parsed_data
    
    # ------------------------------------------------------------
    # 5. parse_device_data() - 解析设备所有模块数据
    # ------------------------------------------------------------
    def parse_device_data(self, device_modules: List[str], db_data: bytes) -> Dict[str, Any]:
        """解析设备的所有模块数据
        
        Args:
            device_modules: 设备包含的模块名称列表
            db_data: DB块的完整数据
            
        Returns:
            解析后的设备数据
        """
        device_data = {
            'timestamp': datetime.now().isoformat(),
            'modules': {}
        }
        
        for module_name in device_modules:
            try:
                module_data = self.parse_module(module_name, db_data)
                device_data['modules'][module_name] = module_data
            except Exception as e:
                print(f"[WARN]  解析模块 {module_name} 失败: {e}")
        
        return device_data


# ============================================================
# 使用示例
# ============================================================
if __name__ == "__main__":
    # 测试解析器
    parser = ModuleParser()
    
    # 模拟从PLC读取的数据 (测试用)
    test_data = bytes([
        # WeighSensor (0-13)
        0xB1, 0xC3,  # GrossWeigh Word
        0xB1, 0xC3,  # NetWeigh Word
        0x00, 0x80,  # StatusWord
        0xFF, 0xFF, 0xB1, 0xC3,  # AdvGrossWeigh DWord
        0xFF, 0xFF, 0xB1, 0xC3,  # AdvNetWeigh DWord
        
        # FlowMeter (14-23)
        0x00, 0x00, 0x00, 0x00,  # RtFlow
        0x00, 0x00, 0x00, 0x00,  # TotalFlow
        0x00, 0x00,  # TotalFlowMilli
        
        # ModbusDevKit (24-31)
        0x00, 0x00,  # VoltageCH1
        0x00, 0x00,  # VoltageCH2
        0x00, 0x00,  # AmpereCH1
        0x00, 0x00,  # AmpereCH2
        
        # WaterMeter (32-39)
        0x00, 0x00, 0x00, 0x00,  # Flow
        0x00, 0x00, 0x00, 0x00,  # TotalFlow
    ])
    
    # 解析设备数据
    device_modules = ['WeighSensor', 'FlowMeter', 'ModbusDevKit', 'WaterMeter']
    result = parser.parse_device_data(device_modules, test_data)
    
    # 打印结果
    import json
    print("\n解析结果:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
