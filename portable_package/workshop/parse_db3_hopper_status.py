# -*- coding: utf-8 -*-
"""
DB3 (料仓设备状态位) 数据块解析 - 独立脚本
包含 9 个料仓的模块通信状态
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
print("DB3 (料仓设备状态位) 数据块解析")
print(f"PLC: {PLC_IP}  Rack: {PLC_RACK}  Slot: {PLC_SLOT}")
print("=" * 100)

try:
    data = client.db_read(3, 0, 148)
    data = bytes(data)

    def parse_module_status(offset):
        """解析模块状态 (4字节)"""
        byte0 = data[offset]
        status_word = struct.unpack(">H", data[offset+2:offset+4])[0]
        
        error = bool(byte0 & 0x01)
        status_str = "ERROR" if error else "OK"
        
        return error, status_word, status_str

    print()
    print("--- 短料仓 (4个) - 有称重 ---")
    print("模块: 称重传感器 + 温度传感器 + 电表 + 电流电表")
    print()

    # 短料仓配置: [(offset, device_name, ui_name)]
    short_hoppers = [
        (0, "short_hopper_1", "7号窑"),
        (16, "short_hopper_3", "5号窑"),
        (32, "short_hopper_2", "6号窑"),
        (48, "short_hopper_4", "4号窑"),
    ]

    for offset, device_name, ui_name in short_hoppers:
        print(f"[{device_name}] {ui_name}")
        
        # 4个模块状态 (每个4字节)
        modules = [
            (offset, "称重传感器"),
            (offset+4, "温度传感器"),
            (offset+8, "电表"),
            (offset+12, "电流电表"),
        ]
        
        for mod_offset, mod_name in modules:
            error, status_word, status_str = parse_module_status(mod_offset)
            print(f"  {mod_name:12s}: Error={error}  Status=0x{status_word:04X}  [{status_str}]")
        print()

    print()
    print("--- 无料仓 (2个) - 无称重 ---")
    print("模块: 温度传感器 + 电表 + 电流电表")
    print()

    # 无料仓配置
    no_hoppers = [
        (64, "no_hopper_1", "2号窑"),
        (76, "no_hopper_2", "1号窑"),
    ]

    for offset, device_name, ui_name in no_hoppers:
        print(f"[{device_name}] {ui_name}")
        
        # 3个模块状态
        modules = [
            (offset, "温度传感器"),
            (offset+4, "电表"),
            (offset+8, "电流电表"),
        ]
        
        for mod_offset, mod_name in modules:
            error, status_word, status_str = parse_module_status(mod_offset)
            print(f"  {mod_name:12s}: Error={error}  Status=0x{status_word:04X}  [{status_str}]")
        print()

    print()
    print("--- 长料仓 (3个) - 有称重+双温度 ---")
    print("模块: 称重传感器 + 温度传感器1 + 温度传感器2 + 电表 + 电流电表")
    print()

    # 长料仓配置
    long_hoppers = [
        (88, "long_hopper_1", "8号窑"),
        (108, "long_hopper_2", "3号窑"),
        (128, "long_hopper_3", "9号窑"),
    ]

    for offset, device_name, ui_name in long_hoppers:
        print(f"[{device_name}] {ui_name}")
        
        # 5个模块状态
        modules = [
            (offset, "称重传感器"),
            (offset+4, "温度传感器1"),
            (offset+8, "温度传感器2"),
            (offset+12, "电表"),
            (offset+16, "电流电表"),
        ]
        
        for mod_offset, mod_name in modules:
            error, status_word, status_str = parse_module_status(mod_offset)
            print(f"  {mod_name:12s}: Error={error}  Status=0x{status_word:04X}  [{status_str}]")
        print()

    print()
    print("--- 原始数据 (每行16字节) ---")
    for i in range(0, 148, 16):
        hex_str = data[i:min(i+16, 148)].hex().upper()
        hex_fmt = " ".join([hex_str[j:j+2] for j in range(0, len(hex_str), 2)])
        print(f"  {i:3d}: {hex_fmt}")

except Exception as e:
    print(f"读取 DB3 失败: {e}")
    import traceback
    traceback.print_exc()

client.disconnect()
print()
print("=" * 100)
print("读取完成")
print("=" * 100)
input("按回车键退出...")

