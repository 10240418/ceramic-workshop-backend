#!/usr/bin/env python3
"""
============================================================
PLC DB10 (SCR/风机) 完整数据流测试
============================================================
数据流: 原始字节 → 解析器 → 转换器 → 存储字段
============================================================
"""
import sys
import struct
sys.path.insert(0, '.')

import snap7
import yaml
from pathlib import Path
from app.tools import get_converter, CONVERTER_MAP

# PLC 配置
IP = "192.168.50.223"
RACK = 0
SLOT = 1
DB_NUMBER = 10
READ_LENGTH = 244  # DB10 总大小

def load_plc_modules():
    """加载 PLC 基础模块配置"""
    config_path = Path("configs/plc_modules.yaml")
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return {m['name']: m for m in config['modules']}

def load_db_config():
    """加载 DB10 配置"""
    config_path = Path("configs/config_scr_fans.yaml")
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def parse_field(data: bytes, field: dict, base_offset: int = 0) -> tuple:
    """解析单个字段"""
    data_type = field['data_type']
    offset = base_offset + field['offset']
    scale = field.get('scale', 1.0)
    
    try:
        if data_type == 'Word':
            raw_value = struct.unpack('>H', data[offset:offset+2])[0]
        elif data_type == 'DWord':
            raw_value = struct.unpack('>I', data[offset:offset+4])[0]
        elif data_type == 'Real':
            raw_value = struct.unpack('>f', data[offset:offset+4])[0]
        elif data_type == 'Int':
            raw_value = struct.unpack('>h', data[offset:offset+2])[0]
        else:
            raw_value = 0
    except:
        raw_value = 0
    
    display_value = raw_value * scale if scale != 1.0 else raw_value
    formula = f"{raw_value} × {scale}" if scale != 1.0 else str(raw_value)
    
    return raw_value, display_value, formula

def parse_module(data: bytes, module_config: dict, base_offset: int = 0) -> dict:
    """解析单个模块"""
    result = {}
    for field in module_config['fields']:
        name = field['name']
        raw_val, display_val, formula = parse_field(data, field, base_offset)
        result[name] = {
            'raw': raw_val,
            'value': display_val,
            'formula': formula,
            'unit': field.get('unit', ''),
            'display_name': field.get('display_name', name),
        }
    return result

def print_hex_bytes(data: bytes, offset: int, length: int):
    """打印十六进制字节"""
    end = min(offset + length, len(data))
    chunk = data[offset:end]
    hex_str = ' '.join(f'{b:02X}' for b in chunk[:32])
    if len(chunk) > 32:
        hex_str += " ..."
    print(f"   原始字节 [{offset:3d}-{end-1:3d}]: {hex_str}")

def process_device(data: bytes, device: dict, modules: dict):
    """处理单个设备"""
    device_id = device['device_id']
    device_name = device['device_name']
    start_offset = device['start_offset']
    
    print(f"\n{'='*70}")
    print(f"📱 {device_name} ({device_id})")
    print(f"   偏移: {start_offset}, 大小: {device['total_size']} bytes")
    print('='*70)
    
    db_fields = {}
    
    for module in device['modules']:
        module_type = module['module_type']
        module_offset = module['offset']
        module_tag = module['tag']
        module_size = module['size']
        desc = module.get('description', module_tag)
        
        print(f"\n   [{module_tag}] {desc} ({module_type}, 偏移: {module_offset})")
        print_hex_bytes(data, module_offset, module_size)
        
        # 解析模块
        module_config = modules[module_type]
        parsed = parse_module(data, module_config, module_offset)
        
        # 打印解析结果
        print(f"   解析结果:")
        for fname, finfo in parsed.items():
            raw_str = f"{finfo['raw']:.4f}" if isinstance(finfo['raw'], float) else str(finfo['raw'])
            print(f"      {finfo['display_name']}: {raw_str} {finfo['unit']}")
        
        # 转换器处理
        if module_type in CONVERTER_MAP:
            converter = get_converter(module_type)
            converter_input = {k: {'value': v['value']} for k, v in parsed.items()}
            converted = converter.convert(converter_input)
            
            print(f"    存储字段: {converted}")
            db_fields[module_tag] = converted
    
    return db_fields

def main():
    print("=" * 70)
    print("PLC DB10 (SCR/风机) 完整数据流测试")
    print("=" * 70)
    
    # 加载配置
    modules = load_plc_modules()
    db_config = load_db_config()
    
    print(f"📋 DB块: {db_config['db_config']['db_name']}")
    print(f"📋 总大小: {db_config['db_config']['total_size']} bytes")
    
    # 连接 PLC
    print(f"\n🔌 连接 PLC: {IP}")
    client = snap7.client.Client()
    
    try:
        client.connect(IP, RACK, SLOT)
        if not client.get_connected():
            print(" PLC 连接失败")
            return
        print(" PLC 连接成功!")
        
        # 读取 DB10
        data = client.db_read(DB_NUMBER, 0, READ_LENGTH)
        print(f" 读取 DB{DB_NUMBER}: {len(data)} 字节")
        
        # 原始数据概览
        print("\n" + "=" * 70)
        print("📦 原始数据概览")
        print("=" * 70)
        for i in range(0, min(128, len(data)), 16):
            chunk = data[i:i+16]
            hex_str = ' '.join(f'{b:02X}' for b in chunk)
            print(f"[{i:4d}] {hex_str}")
        
        all_fields = {}
        
        # ========================================
        # 处理 SCR 设备 (2个)
        # ========================================
        print("\n" + "#" * 70)
        print("# SCR 设备 (2个) - 燃气表 + 电表")
        print("#" * 70)
        
        for device in db_config['scr_devices']:
            fields = process_device(data, device, modules)
            all_fields[device['device_id']] = fields
        
        # ========================================
        # 处理风机 (2个)
        # ========================================
        print("\n" + "#" * 70)
        print("# 风机 (2个) - 电表")
        print("#" * 70)
        
        for device in db_config['fans']:
            fields = process_device(data, device, modules)
            all_fields[device['device_id']] = fields
        
        # 汇总
        print("\n" + "=" * 70)
        print("💾 数据库存储汇总")
        print("=" * 70)
        for device_id, fields in all_fields.items():
            print(f"\n{device_id}:")
            for module_tag, module_fields in fields.items():
                if 'flow_rate' in module_fields:
                    print(f"   [{module_tag}] flow_rate={module_fields['flow_rate']:.4f} m³/h, total_flow={module_fields['total_flow']:.3f} m³")
                else:
                    print(f"   [{module_tag}] Pt={module_fields['Pt']:.2f}kW, ImpEp={module_fields['ImpEp']:.2f}kWh")
        
        print("\n" + "=" * 70)
        print(" DB10 数据流测试完成!")
        print("=" * 70)
        
    except Exception as e:
        print(f" 错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if client.get_connected():
            client.disconnect()
            print("\n🔌 PLC 连接已关闭")

if __name__ == "__main__":
    main()
