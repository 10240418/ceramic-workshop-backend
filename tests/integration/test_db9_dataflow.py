#!/usr/bin/env python3
"""
============================================================
PLC DB9 (辊道窑) 完整数据流测试
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
DB_NUMBER = 9
READ_LENGTH = 348  # DB9 总大小

def load_plc_modules():
    """加载 PLC 基础模块配置"""
    config_path = Path("configs/plc_modules.yaml")
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return {m['name']: m for m in config['modules']}

def load_db_config():
    """加载 DB9 配置"""
    config_path = Path("configs/config_roller_kiln.yaml")
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

def main():
    print("=" * 70)
    print("PLC DB9 (辊道窑) 完整数据流测试")
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
            print("❌ PLC 连接失败")
            return
        print("✅ PLC 连接成功!")
        
        # 读取 DB9
        data = client.db_read(DB_NUMBER, 0, READ_LENGTH)
        print(f"✅ 读取 DB{DB_NUMBER}: {len(data)} 字节")
        
        # 原始数据概览
        print("\n" + "=" * 70)
        print("📦 原始数据概览")
        print("=" * 70)
        for i in range(0, min(128, len(data)), 16):
            chunk = data[i:i+16]
            hex_str = ' '.join(f'{b:02X}' for b in chunk)
            print(f"[{i:4d}] {hex_str}")
        
        db_fields = {}
        roller_kiln = db_config['roller_kiln']
        device_id = roller_kiln['device_id']
        
        print(f"\n{'='*70}")
        print(f"📱 {roller_kiln['device_name']} ({device_id})")
        print('='*70)
        
        # ========================================
        # 处理温度传感器 (6个)
        # ========================================
        print("\n" + "-" * 50)
        print("🌡️  温度传感器 (6个温区)")
        print("-" * 50)
        
        for sensor in roller_kiln['temperature_sensors']:
            module_type = sensor['module_type']
            offset = sensor['offset']
            tag = sensor['tag']
            desc = sensor.get('description', tag)
            
            print(f"\n   [{tag}] {desc} (偏移: {offset})")
            print_hex_bytes(data, offset, 2)
            
            # 解析
            module_config = modules[module_type]
            parsed = parse_module(data, module_config, offset)
            
            for fname, finfo in parsed.items():
                print(f"      原始值: {finfo['raw']}, 计算: {finfo['formula']}")
            
            # 转换
            if module_type in CONVERTER_MAP:
                converter = get_converter(module_type)
                converter_input = {k: {'value': v['value']} for k, v in parsed.items()}
                converted = converter.convert(converter_input)
                print(f"   ✅ 存储: {converted}")
                db_fields[tag] = converted
        
        # ========================================
        # 处理电表 (6个)
        # ========================================
        print("\n" + "-" * 50)
        print("⚡ 电表 (主电表 + 5个分区电表)")
        print("-" * 50)
        
        for meter in roller_kiln['electricity_meters']:
            module_type = meter['module_type']
            offset = meter['offset']
            tag = meter['tag']
            desc = meter.get('description', tag)
            
            print(f"\n   [{tag}] {desc} (偏移: {offset})")
            print_hex_bytes(data, offset, 56)
            
            # 解析
            module_config = modules[module_type]
            parsed = parse_module(data, module_config, offset)
            
            # 只打印关键字段
            key_fields = ['Pt', 'ImpEp', 'Ua_0', 'I_0']
            for fname in key_fields:
                if fname in parsed:
                    finfo = parsed[fname]
                    val = f"{finfo['raw']:.2f}" if isinstance(finfo['raw'], float) else str(finfo['raw'])
                    print(f"      {finfo['display_name']}: {val} {finfo['unit']}")
            
            # 转换
            if module_type in CONVERTER_MAP:
                converter = get_converter(module_type)
                converter_input = {k: {'value': v['value']} for k, v in parsed.items()}
                converted = converter.convert(converter_input)
                print(f"   ✅ 存储: Pt={converted['Pt']:.2f}kW, ImpEp={converted['ImpEp']:.2f}kWh")
                db_fields[tag] = converted
        
        # 汇总
        print("\n" + "=" * 70)
        print("💾 数据库存储汇总")
        print("=" * 70)
        print(f"\n{device_id}:")
        for tag, fields in db_fields.items():
            if 'temperature' in fields:
                print(f"   [{tag}] temperature={fields['temperature']:.1f}°C")
            else:
                print(f"   [{tag}] Pt={fields['Pt']:.2f}kW, ImpEp={fields['ImpEp']:.2f}kWh")
        
        print("\n" + "=" * 70)
        print("✅ DB9 数据流测试完成!")
        print("=" * 70)
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if client.get_connected():
            client.disconnect()
            print("\n🔌 PLC 连接已关闭")

if __name__ == "__main__":
    main()
