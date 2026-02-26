# -*- coding: utf-8 -*-
"""DB32 (MODBUS_DATA_VALUE) - 电炉传感器数据块解析 (独立脚本, 无外部依赖)"""

import struct
import sys

try:
    import snap7
except ImportError:
    print("snap7 not installed, run: pip install python-snap7")
    sys.exit(1)

# PLC 连接配置 (根据实际情况修改)
PLC_IP = "192.168.1.10"
PLC_RACK = 0
PLC_SLOT = 1

client = snap7.client.Client()

try:
    client.connect(PLC_IP, PLC_RACK, PLC_SLOT)
except Exception as e:
    print(f"PLC connect failed: {e}")
    sys.exit(1)

print("=" * 80)
print("DB32 (MODBUS_DATA_VALUE) - 电炉传感器数据块")
print(f"PLC: {PLC_IP}  Rack: {PLC_RACK}  Slot: {PLC_SLOT}")
print("=" * 80)

try:
    # DB32 总大小: 21 字节 (offset 0~20)
    data = client.db_read(32, 0, 21)
    data = bytes(data)

    print()
    print("--- 红外测距数据解析 (3个电极深度) ---")
    print()

    # LENTH1 (UDInt, 4字节, offset 0)
    lenth1 = struct.unpack(">I", data[0:4])[0]
    print(f"[1号电极] LENTH1 (Offset 0-3)")
    print(f"  原始值: {lenth1}  (0x{lenth1:08X})")
    print(f"  深度值: {lenth1} mm")
    print()

    # LENTH2 (UDInt, 4字节, offset 4)
    lenth2 = struct.unpack(">I", data[4:8])[0]
    print(f"[2号电极] LENTH2 (Offset 4-7)")
    print(f"  原始值: {lenth2}  (0x{lenth2:08X})")
    print(f"  深度值: {lenth2} mm")
    print()

    # LENTH3 (UDInt, 4字节, offset 8)
    lenth3 = struct.unpack(">I", data[8:12])[0]
    print(f"[3号电极] LENTH3 (Offset 8-11)")
    print(f"  原始值: {lenth3}  (0x{lenth3:08X})")
    print(f"  深度值: {lenth3} mm")
    print()

    print()
    print("--- 压力计数据解析 (2个冷却水压力) ---")
    print()

    # WATER_PRESS_1 (Int, 2字节, offset 12)
    water_press_1 = struct.unpack(">h", data[12:14])[0]
    print(f"[炉皮侧压力] WATER_PRESS_1 (Offset 12-13)")
    print(f"  原始值: {water_press_1}  (0x{water_press_1 & 0xFFFF:04X})")
    print(f"  压力值: {water_press_1} kPa")
    print()

    # WATER_PRESS_2 (Int, 2字节, offset 14)
    water_press_2 = struct.unpack(">h", data[14:16])[0]
    print(f"[炉盖侧压力] WATER_PRESS_2 (Offset 14-15)")
    print(f"  原始值: {water_press_2}  (0x{water_press_2 & 0xFFFF:04X})")
    print(f"  压力值: {water_press_2} kPa")
    print()

    # 计算前置过滤器压差
    pressure_diff = water_press_1 - water_press_2
    print(f"[前置过滤器压差] = 炉皮压力 - 炉盖压力")
    print(f"  压差值: {pressure_diff} kPa")
    print()

    print()
    print("--- 流量计数据解析 (2个冷却水流量) ---")
    print()

    # WATER_FLOW_1 (Int, 2字节, offset 16)
    water_flow_1_raw = struct.unpack(">h", data[16:18])[0]
    water_flow_1 = water_flow_1_raw * 1.0  # 转换为 m³/h
    print(f"[炉皮冷却水流量] WATER_FLOW_1 (Offset 16-17)")
    print(f"  原始值: {water_flow_1_raw}  (0x{water_flow_1_raw & 0xFFFF:04X})")
    print(f"  流量值: {water_flow_1:.1f} m³/h")
    print()

    # WATER_FLOW_2 (Int, 2字节, offset 18)
    water_flow_2_raw = struct.unpack(">h", data[18:20])[0]
    water_flow_2 = water_flow_2_raw * 1.0  # 转换为 m³/h
    print(f"[炉盖冷却水流量] WATER_FLOW_2 (Offset 18-19)")
    print(f"  原始值: {water_flow_2_raw}  (0x{water_flow_2_raw & 0xFFFF:04X})")
    print(f"  流量值: {water_flow_2:.1f} m³/h")
    print()

    print()
    print("--- 蝶阀状态监测 (4个蝶阀) ---")
    print()

    # ValveStatus (Byte, 1字节, offset 20)
    valve_status = data[20]
    print(f"[蝶阀状态] ValveStatus (Offset 20)")
    print(f"  原始值: {valve_status}  (0x{valve_status:02X} = {valve_status:08b}b)")
    print()

    # 解析每个蝶阀状态 (每2个bit对应一个蝶阀)
    valves = [
        ("蝶阀1", 0, 1),  # bit0(关), bit1(开)
        ("蝶阀2", 2, 3),  # bit2(关), bit3(开)
        ("蝶阀3", 4, 5),  # bit4(关), bit5(开)
        ("蝶阀4", 6, 7),  # bit6(关), bit7(开)
    ]

    for valve_name, close_bit, open_bit in valves:
        is_closed = bool(valve_status & (1 << close_bit))
        is_open = bool(valve_status & (1 << open_bit))
        
        if is_open and not is_closed:
            status = "开启"
        elif is_closed and not is_open:
            status = "关闭"
        elif is_open and is_closed:
            status = "异常(同时开关)"
        else:
            status = "未知"
        
        print(f"  {valve_name}: bit{close_bit}(关)={is_closed}  bit{open_bit}(开)={is_open}  [{status}]")
    print()

    print()
    print("--- 原始数据 (全部21字节) ---")
    hex_str = data.hex().upper()
    hex_fmt = " ".join([hex_str[j : j + 2] for j in range(0, len(hex_str), 2)])
    print(f"  0: {hex_fmt}")
    print()

except Exception as e:
    print(f"Read DB32 failed: {e}")
    import traceback
    traceback.print_exc()

client.disconnect()
print()
print("=" * 80)
print("读取完成")
print("=" * 80)
input("按回车键退出...")

