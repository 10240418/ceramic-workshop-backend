# -*- coding: utf-8 -*-
"""DB1 (MBValueTemp) - Modbus 主站通信状态数据块解析 (独立脚本, 无外部依赖)"""

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
print("DB1 (MBValueTemp) - Modbus 主站通信状态数据块")
print(f"PLC: {PLC_IP}  Rack: {PLC_RACK}  Slot: {PLC_SLOT}")
print("=" * 80)

try:
    data = client.db_read(1, 0, 80)
    data = bytes(data)

    print()
    print("--- 主站状态模块解析 (每个4字节: Done/Busy/Error/Status) ---")
    print()

    devices = [
        (0, "主站通信负载", "MB_COMM_LOAD"),
        (4, "电表1主站状态", "DB_MASTER_ELEC_0"),
        (8, "电表2主站状态", "DB_MASTER_ELEC_1"),
        (12, "电表3主站状态", "DB_MASTER_ELEC_2"),
        (16, "电表4主站状态", "DB_MASTER_ELEC_3"),
        (20, "电表5主站状态", "DB_MASTER_ELEC_4"),
        (24, "电表6主站状态", "DB_MASTER_ELEC_5"),
        (28, "电表7主站状态", "DB_MASTER_ELEC_6"),
        (32, "电表8主站状态", "DB_MASTER_ELEC_7"),
        (36, "电表9主站状态", "DB_MASTER_ELEC_8"),
        (40, "电表10主站状态", "DB_MASTER_ELEC_9"),
        (44, "电表11主站状态", "DB_MASTER_ELEC_10"),
        (48, "电表12主站状态", "DB_MASTER_ELEC_11"),
        (52, "总管压力主站状态", "DB_MASTER_PRESS"),
        (56, "1号泵震动主站状态", "DB_MASTER_VIB_1"),
        (60, "2号泵震动主站状态", "DB_MASTER_VIB_2"),
        (64, "3号泵震动主站状态", "DB_MASTER_VIB_3"),
        (68, "4号泵震动主站状态", "DB_MASTER_VIB_4"),
        (72, "5号泵震动主站状态", "DB_MASTER_VIB_5"),
        (76, "6号泵震动主站状态", "DB_MASTER_VIB_6"),
    ]

    for offset, name, plc_name in devices:
        byte0 = data[offset]
        status_word = struct.unpack(">H", data[offset + 2 : offset + 4])[0]

        done = bool(byte0 & 0x01)
        busy = bool(byte0 & 0x02)
        error = bool(byte0 & 0x04)

        status_str = "OK" if not error else "ERROR"
        if busy:
            status_str = "BUSY"

        print(f"[Offset {offset:2d}] {name:20s} ({plc_name})")
        print(
            f"  Done={done}  Busy={busy}  Error={error}  Status=0x{status_word:04X}  [{status_str}]"
        )
        print(f"  Byte0: 0x{byte0:02X} = {byte0:08b}b")
        print()

    print()
    print("--- 原始数据 (每行16字节) ---")
    for i in range(0, 80, 16):
        hex_str = data[i : min(i + 16, 80)].hex().upper()
        hex_fmt = " ".join([hex_str[j : j + 2] for j in range(0, len(hex_str), 2)])
        print(f"  {i:3d}: {hex_fmt}")

except Exception as e:
    print(f"Read DB1 failed: {e}")
    import traceback
    traceback.print_exc()

client.disconnect()
print()
print("=" * 80)
print("读取完成")
print("=" * 80)
input("按回车键退出...")
