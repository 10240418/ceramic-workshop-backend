# -*- coding: utf-8 -*-
"""DB3 (DataState) - 设备通信从站状态数据块解析 (独立脚本, 无外部依赖)"""

import struct
import sys

try:
    import snap7
except ImportError:
    print("snap7 not installed, run: pip install python-snap7")
    sys.exit(1)

# PLC 连接配置 (根据实际情况修改)
PLC_IP = "192.168.50.224"
PLC_RACK = 0
PLC_SLOT = 1

client = snap7.client.Client()

try:
    client.connect(PLC_IP, PLC_RACK, PLC_SLOT)
except Exception as e:
    print(f"PLC connect failed: {e}")
    sys.exit(1)

print("=" * 80)
print("DB3 (DataState) - 设备通信从站状态数据块")
print(f"PLC: {PLC_IP}  Rack: {PLC_RACK}  Slot: {PLC_SLOT}")
print("=" * 80)

try:
    data = client.db_read(3, 0, 80)
    data = bytes(data)

    print()
    print("--- 从站状态模块解析 (每个4字节: Error/Status) ---")
    print()

    devices = [
        (0, "电表1状态", "ElectricityMeter_0"),
        (4, "电表2状态", "ElectricityMeter_1"),
        (8, "电表3状态", "ElectricityMeter_2"),
        (12, "电表4状态", "ElectricityMeter_3"),
        (16, "电表5状态", "ElectricityMeter_4"),
        (20, "电表6状态", "ElectricityMeter_5"),
        (24, "电表7状态", "ElectricityMeter_6"),
        (28, "电表8状态", "ElectricityMeter_7"),
        (32, "电表9状态", "ElectricityMeter_8"),
        (36, "电表10状态", "ElectricityMeter_9"),
        (40, "电表11状态", "ElectricityMeter_10"),
        (44, "电表12状态", "ElectricityMeter_11"),
        (52, "总管压力状态", "PRESS"),
        (56, "1号泵震动状态", "VIB_1"),
        (60, "2号泵震动状态", "VIB_2"),
        (64, "3号泵震动状态", "VIB_3"),
        (68, "4号泵震动状态", "VIB_4"),
        (72, "5号泵震动状态", "VIB_5"),
        (76, "6号泵震动状态", "VIB_6"),
    ]

    for offset, name, plc_name in devices:
        byte0 = data[offset]
        status_word = struct.unpack(">H", data[offset + 2 : offset + 4])[0]

        error = bool(byte0 & 0x01)

        status_str = "OK" if not error and status_word == 0 else "ERROR"

        print(f"[Offset {offset:2d}] {name:20s} ({plc_name})")
        print(f"  Error={error}  Status=0x{status_word:04X}  [{status_str}]")
        print(f"  Byte0: 0x{byte0:02X} = {byte0:08b}b")
        print()

    print()
    print("--- 原始数据 (每行16字节) ---")
    for i in range(0, 80, 16):
        hex_str = data[i : min(i + 16, 80)].hex().upper()
        hex_fmt = " ".join([hex_str[j : j + 2] for j in range(0, len(hex_str), 2)])
        print(f"  {i:3d}: {hex_fmt}")

except Exception as e:
    print(f"Read DB3 failed: {e}")
    import traceback
    traceback.print_exc()

client.disconnect()
print()
print("=" * 80)
print("读取完成")
print("=" * 80)
input("按回车键退出...")
