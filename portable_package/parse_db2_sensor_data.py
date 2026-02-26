# -*- coding: utf-8 -*-
"""DB2 (Data_DB) - 传感器实际数据块解析 (独立脚本, 无外部依赖)"""

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
print("DB2 (Data_DB) - 传感器实际数据块")
print(f"PLC: {PLC_IP}  Rack: {PLC_RACK}  Slot: {PLC_SLOT}")
print("=" * 80)

try:
    data = client.db_read(2, 0, 1034)
    data = bytes(data)

    print()
    print("--- 电表数据解析 (6个电表, 每个56字节) ---")
    print()

    for i in range(6):
        offset = i * 56
        print(f"[电表 {i+1}] Offset {offset}-{offset+55}")

        Uab_0 = struct.unpack(">f", data[offset + 0 : offset + 4])[0]
        Uab_1 = struct.unpack(">f", data[offset + 4 : offset + 8])[0]
        Uab_2 = struct.unpack(">f", data[offset + 8 : offset + 12])[0]

        Ua_0 = struct.unpack(">f", data[offset + 12 : offset + 16])[0]
        Ua_1 = struct.unpack(">f", data[offset + 16 : offset + 20])[0]
        Ua_2 = struct.unpack(">f", data[offset + 20 : offset + 24])[0]

        I_0 = struct.unpack(">f", data[offset + 24 : offset + 28])[0]
        I_1 = struct.unpack(">f", data[offset + 28 : offset + 32])[0]
        I_2 = struct.unpack(">f", data[offset + 32 : offset + 36])[0]

        Pt = struct.unpack(">f", data[offset + 36 : offset + 40])[0]
        Pa = struct.unpack(">f", data[offset + 40 : offset + 44])[0]
        Pb = struct.unpack(">f", data[offset + 44 : offset + 48])[0]
        Pc = struct.unpack(">f", data[offset + 48 : offset + 52])[0]

        ImpEp = struct.unpack(">f", data[offset + 52 : offset + 56])[0]

        print(
            f"  AB线电压: {Uab_0:7.2f} V  BC线电压: {Uab_1:7.2f} V  CA线电压: {Uab_2:7.2f} V"
        )
        print(
            f"  A相电压:  {Ua_0:7.2f} V  B相电压:  {Ua_1:7.2f} V  C相电压:  {Ua_2:7.2f} V"
        )
        print(
            f"  A相电流:  {I_0:7.2f} A  B相电流:  {I_1:7.2f} A  C相电流:  {I_2:7.2f} A"
        )
        print(
            f"  总功率:   {Pt:7.2f} kW  A相功率: {Pa:7.2f} kW  B相功率: {Pb:7.2f} kW  C相功率: {Pc:7.2f} kW"
        )
        print(f"  累计电能: {ImpEp:7.2f} kWh")
        print()

    print()
    print("--- 压力传感器数据解析 (Offset 336-337) ---")
    print()

    pressure_raw = struct.unpack(">H", data[336:338])[0]
    pressure_kpa = pressure_raw * 0.01
    print(f"[压力表] Offset 336-337")
    print(f"  原始值: {pressure_raw}  (0x{pressure_raw:04X})")
    print(f"  压力值: {pressure_kpa:.2f} kPa")
    print()

    print()
    print("--- 振动传感器数据解析 (6个振动, 每个116字节) ---")
    print()

    vib_offsets = [338, 454, 570, 686, 802, 918]
    for i, vib_offset in enumerate(vib_offsets):
        print(f"[振动 {i+1}] Offset {vib_offset}-{vib_offset+115}")

        VX = struct.unpack(">H", data[vib_offset + 12 : vib_offset + 14])[0]
        VY = struct.unpack(">H", data[vib_offset + 14 : vib_offset + 16])[0]
        VZ = struct.unpack(">H", data[vib_offset + 16 : vib_offset + 18])[0]

        DX = struct.unpack(">H", data[vib_offset + 26 : vib_offset + 28])[0]
        DY = struct.unpack(">H", data[vib_offset + 28 : vib_offset + 30])[0]
        DZ = struct.unpack(">H", data[vib_offset + 30 : vib_offset + 32])[0]

        HZX = struct.unpack(">H", data[vib_offset + 32 : vib_offset + 34])[0]
        HZY = struct.unpack(">H", data[vib_offset + 34 : vib_offset + 36])[0]
        HZZ = struct.unpack(">H", data[vib_offset + 36 : vib_offset + 38])[0]

        print(
            f"  速度幅值: VX={VX:5d} mm/s  VY={VY:5d} mm/s  VZ={VZ:5d} mm/s"
        )
        print(
            f"  位移幅值: DX={DX:5d} um     DY={DY:5d} um     DZ={DZ:5d} um"
        )
        print(
            f"  频率:     HZX={HZX:5d} Hz    HZY={HZY:5d} Hz    HZZ={HZZ:5d} Hz"
        )
        print()

    print()
    print("--- 原始数据 (前256字节, 每行16字节) ---")
    for i in range(0, min(256, 1034), 16):
        hex_str = data[i : min(i + 16, 1034)].hex().upper()
        hex_fmt = " ".join([hex_str[j : j + 2] for j in range(0, len(hex_str), 2)])
        print(f"  {i:3d}: {hex_fmt}")

    print()
    print("... (省略后续数据)")

except Exception as e:
    print(f"Read DB2 failed: {e}")
    import traceback
    traceback.print_exc()

client.disconnect()
print()
print("=" * 80)
print("读取完成")
print("=" * 80)
input("按回车键退出...")
