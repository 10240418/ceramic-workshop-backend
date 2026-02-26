# -*- coding: utf-8 -*-
"""
DB7 (辊道窑设备状态位) 数据块解析 - 独立脚本
包含 6个温度传感器状态 + 6组电表状态
每个模块状态: Error(Bool) + Status(Word) = 4字节
"""

import struct
import sys

try:
    import snap7
except ImportError:
    print("snap7 未安装，请运行: pip install python-snap7")
    sys.exit(1)

# PLC 连接配置
PLC_IP = "192.168.50.223"
PLC_RACK = 0
PLC_SLOT = 1

client = snap7.client.Client()

try:
    client.connect(PLC_IP, PLC_RACK, PLC_SLOT)
except Exception as e:
    print(f"PLC 连接失败: {e}")
    sys.exit(1)

print("=" * 100)
print("DB7 (辊道窑设备状态位) 数据块解析")
print(f"PLC: {PLC_IP}  Rack: {PLC_RACK}  Slot: {PLC_SLOT}")
print("=" * 100)

try:
    data = client.db_read(7, 0, 72)
    data = bytes(data)

    def parse_module_status(offset):
        """解析模块状态 (4字节)"""
        byte0 = data[offset]
        status_word = struct.unpack(">H", data[offset+2:offset+4])[0]
        
        error = bool(byte0 & 0x01)
        status_str = "ERROR" if error else "OK"
        
        return error, status_word, status_str

    print()
    print("--- 温度传感器状态 (6个) ---")
    print()

    # 温度传感器配置: [(offset, zone_name)]
    temp_sensors = [
        (0, "1号温区"),
        (4, "2号温区"),
        (8, "3号温区"),
        (12, "4号温区"),
        (16, "5号温区"),
        (20, "6号温区"),
    ]

    for offset, zone_name in temp_sensors:
        error, status_word, status_str = parse_module_status(offset)
        print(f"[{zone_name}温度传感器]")
        print(f"  Error={error}  Status=0x{status_word:04X}  [{status_str}]")
        print()

    print()
    print("--- 电表状态 (6组，每组2个模块) ---")
    print("模块: 电表 + 电能电表")
    print()

    # 电表配置: [(offset, zone_name)]
    # 每组电表有2个模块状态 (电表+电能电表)
    meter_groups = [
        (24, "1号温区"),
        (32, "2号温区"),
        (40, "3号温区"),
        (48, "4号温区"),
        (56, "5号温区"),
        (64, "6号温区"),
    ]

    for offset, zone_name in meter_groups:
        print(f"[{zone_name}电表]")
        
        # 2个模块状态
        modules = [
            (offset, "电表"),
            (offset+4, "电能电表"),
        ]
        
        for mod_offset, mod_name in modules:
            error, status_word, status_str = parse_module_status(mod_offset)
            print(f"  {mod_name:12s}: Error={error}  Status=0x{status_word:04X}  [{status_str}]")
        print()

    print()
    print("--- 原始数据 (每行16字节) ---")
    for i in range(0, 72, 16):
        hex_str = data[i:min(i+16, 72)].hex().upper()
        hex_fmt = " ".join([hex_str[j:j+2] for j in range(0, len(hex_str), 2)])
        print(f"  {i:3d}: {hex_fmt}")

except Exception as e:
    print(f"读取 DB7 失败: {e}")
    import traceback
    traceback.print_exc()

client.disconnect()
print()
print("=" * 100)
print("读取完成")
print("=" * 100)
input("按回车键退出...")

