# -*- coding: utf-8 -*-
"""
DB9 (辊道窑) 数据块解析 - 独立脚本
包含 6 个温区，每个温区有温度传感器和电表
应用数据转换: 温度×0.1, 电流×0.001×60, 功率×0.0001×60, 能耗×2
注意: 辊道窑电流变比=60 (与料仓不同)
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
print("DB9 (辊道窑) 数据块解析")
print(f"PLC: {PLC_IP}  Rack: {PLC_RACK}  Slot: {PLC_SLOT}")
print("=" * 100)

try:
    data = client.db_read(9, 0, 348)
    data = bytes(data)

    print()
    print("--- 辊道窑 6 温区数据 ---")
    print()

    # 温区配置: [(temp_offset, meter_offset, zone_name)]
    zones = [
        (0, 12, "1号温区"),
        (2, 68, "2号温区"),
        (4, 124, "3号温区"),
        (6, 180, "4号温区"),
        (8, 236, "5号温区"),
        (10, 292, "6号温区"),
    ]

    for temp_offset, meter_offset, zone_name in zones:
        # 温度传感器 (2字节)
        temp_raw = struct.unpack(">h", data[temp_offset:temp_offset+2])[0]
        temp = temp_raw * 0.1
        
        # 电表 (56字节)
        # 电表字段偏移 (相对于电表起始位置):
        # Ua_0: +4, I_0: +16, I_1: +20, I_2: +24, Pt: +40, ImpEp: +52
        pt_raw = struct.unpack(">f", data[meter_offset+40:meter_offset+44])[0]
        impe_raw = struct.unpack(">f", data[meter_offset+52:meter_offset+56])[0]
        ua_raw = struct.unpack(">f", data[meter_offset+4:meter_offset+8])[0]
        i0_raw = struct.unpack(">f", data[meter_offset+16:meter_offset+20])[0]
        i1_raw = struct.unpack(">f", data[meter_offset+20:meter_offset+24])[0]
        i2_raw = struct.unpack(">f", data[meter_offset+24:meter_offset+28])[0]
        
        # 应用转换公式 (辊道窑电流变比=60)
        pt = pt_raw * 0.0001 * 60
        impe = impe_raw * 2
        ua = ua_raw * 0.1
        i0 = i0_raw * 0.001 * 60
        i1 = i1_raw * 0.001 * 60
        i2 = i2_raw * 0.001 * 60
        
        print(f"[{zone_name}]")
        print(f"  温度: {temp:.1f}°C")
        print(f"  电表: 功率={pt:.2f}kW, 能耗={impe:.1f}kWh, 电压={ua:.1f}V")
        print(f"        电流: A相={i0:.1f}A, B相={i1:.1f}A, C相={i2:.1f}A")
        print()

    print()
    print("--- 原始数据 (每行16字节) ---")
    for i in range(0, 348, 16):
        hex_str = data[i:min(i+16, 348)].hex().upper()
        hex_fmt = " ".join([hex_str[j:j+2] for j in range(0, len(hex_str), 2)])
        print(f"  {i:3d}: {hex_fmt}")

except Exception as e:
    print(f"读取 DB9 失败: {e}")
    import traceback
    traceback.print_exc()

client.disconnect()
print()
print("=" * 100)
print("读取完成")
print("=" * 100)
input("按回车键退出...")

