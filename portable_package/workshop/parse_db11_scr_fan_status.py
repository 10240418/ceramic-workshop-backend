# -*- coding: utf-8 -*-
"""
DB11 (SCR设备和风机状态位) 数据块解析 - 独立脚本
包含 2个SCR设备状态 + 2个风机状态
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
print("DB11 (SCR设备和风机状态位) 数据块解析")
print(f"PLC: {PLC_IP}  Rack: {PLC_RACK}  Slot: {PLC_SLOT}")
print("=" * 100)

try:
    data = client.db_read(11, 0, 40)
    data = bytes(data)

    def parse_module_status(offset):
        """解析模块状态 (4字节)"""
        byte0 = data[offset]
        status_word = struct.unpack(">H", data[offset+2:offset+4])[0]
        
        error = bool(byte0 & 0x01)
        status_str = "ERROR" if error else "OK"
        
        return error, status_word, status_str

    print()
    print("--- SCR 设备状态 (2个) ---")
    print("模块: 流量计 + 电表 + 电能电表")
    print()

    # SCR配置: [(offset, device_name, meter_name)]
    scr_devices = [
        (0, "1号SCR", "氨泵1电表(表63)"),
        (12, "2号SCR", "氨泵2电表(表66)"),
    ]

    for offset, device_name, meter_name in scr_devices:
        print(f"[{device_name}] {meter_name}")
        
        # 3个模块状态
        modules = [
            (offset, "流量计"),
            (offset+4, "电表"),
            (offset+8, "电能电表"),
        ]
        
        for mod_offset, mod_name in modules:
            error, status_word, status_str = parse_module_status(mod_offset)
            print(f"  {mod_name:12s}: Error={error}  Status=0x{status_word:04X}  [{status_str}]")
        print()

    print()
    print("--- 风机状态 (2个) ---")
    print("模块: 电表 + 电能电表")
    print()

    # 风机配置: [(offset, device_name, meter_name)]
    fans = [
        (24, "1号风机", "风机1电表(表64)"),
        (32, "2号风机", "风机2电表(表65)"),
    ]

    for offset, device_name, meter_name in fans:
        print(f"[{device_name}] {meter_name}")
        
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
    for i in range(0, 40, 16):
        hex_str = data[i:min(i+16, 40)].hex().upper()
        hex_fmt = " ".join([hex_str[j:j+2] for j in range(0, len(hex_str), 2)])
        print(f"  {i:3d}: {hex_fmt}")

except Exception as e:
    print(f"读取 DB11 失败: {e}")
    import traceback
    traceback.print_exc()

client.disconnect()
print()
print("=" * 100)
print("读取完成")
print("=" * 100)
input("按回车键退出...")

