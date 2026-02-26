# -*- coding: utf-8 -*-
"""
DB10 (SCR设备和风机) 数据块解析 - 独立脚本
包含 2个SCR设备 + 2个风机
应用数据转换: 流量×0.1, 累计流量×1, 电流×0.001×20, 功率×0.0001×20, 能耗×2
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
print("DB10 (SCR设备和风机) 数据块解析")
print(f"PLC: {PLC_IP}  Rack: {PLC_RACK}  Slot: {PLC_SLOT}")
print("=" * 100)

try:
    data = client.db_read(10, 0, 244)
    data = bytes(data)

    print()
    print("--- SCR 设备 (2个) - 燃气表+电表 ---")
    print()

    # SCR配置: [(gas_offset, meter_offset, device_name, meter_name)]
    scr_devices = [
        (0, 10, "1号SCR", "氨泵1电表(表63)"),
        (66, 188, "2号SCR", "氨泵2电表(表66)"),
    ]

    for gas_offset, meter_offset, device_name, meter_name in scr_devices:
        # 燃气表 (10字节)
        flow_rate_raw = struct.unpack(">f", data[gas_offset:gas_offset+4])[0]
        total_flow_raw = struct.unpack(">f", data[gas_offset+4:gas_offset+8])[0]
        
        flow_rate = flow_rate_raw * 0.1
        total_flow = total_flow_raw * 1.0
        
        # 电表 (56字节)
        pt_raw = struct.unpack(">f", data[meter_offset+40:meter_offset+44])[0]
        impe_raw = struct.unpack(">f", data[meter_offset+52:meter_offset+56])[0]
        ua_raw = struct.unpack(">f", data[meter_offset+4:meter_offset+8])[0]
        i0_raw = struct.unpack(">f", data[meter_offset+16:meter_offset+20])[0]
        i1_raw = struct.unpack(">f", data[meter_offset+20:meter_offset+24])[0]
        i2_raw = struct.unpack(">f", data[meter_offset+24:meter_offset+28])[0]
        
        # 应用转换公式 (SCR电流变比=20)
        pt = pt_raw * 0.0001 * 20
        impe = impe_raw * 2
        ua = ua_raw * 0.1
        i0 = i0_raw * 0.001 * 20
        i1 = i1_raw * 0.001 * 20
        i2 = i2_raw * 0.001 * 20
        
        print(f"[{device_name}]")
        print(f"  燃气: 流量={flow_rate:.1f}m³/h, 累计={total_flow:.1f}m³")
        print(f"  {meter_name}: 功率={pt:.2f}kW, 能耗={impe:.1f}kWh, 电压={ua:.1f}V")
        print(f"                电流: A相={i0:.1f}A, B相={i1:.1f}A, C相={i2:.1f}A")
        print()

    print()
    print("--- 风机 (2个) - 仅电表 ---")
    print()

    # 风机配置: [(meter_offset, device_name, meter_name)]
    fans = [
        (76, "1号风机", "风机1电表(表64)"),
        (132, "2号风机", "风机2电表(表65)"),
    ]

    for meter_offset, device_name, meter_name in fans:
        # 电表 (56字节)
        pt_raw = struct.unpack(">f", data[meter_offset+40:meter_offset+44])[0]
        impe_raw = struct.unpack(">f", data[meter_offset+52:meter_offset+56])[0]
        ua_raw = struct.unpack(">f", data[meter_offset+4:meter_offset+8])[0]
        i0_raw = struct.unpack(">f", data[meter_offset+16:meter_offset+20])[0]
        i1_raw = struct.unpack(">f", data[meter_offset+20:meter_offset+24])[0]
        i2_raw = struct.unpack(">f", data[meter_offset+24:meter_offset+28])[0]
        
        # 应用转换公式 (风机电流变比=20)
        pt = pt_raw * 0.0001 * 20
        impe = impe_raw * 2
        ua = ua_raw * 0.1
        i0 = i0_raw * 0.001 * 20
        i1 = i1_raw * 0.001 * 20
        i2 = i2_raw * 0.001 * 20
        
        print(f"[{device_name}]")
        print(f"  {meter_name}: 功率={pt:.2f}kW, 能耗={impe:.1f}kWh, 电压={ua:.1f}V")
        print(f"                电流: A相={i0:.1f}A, B相={i1:.1f}A, C相={i2:.1f}A")
        print()

    print()
    print("--- 原始数据 (每行16字节) ---")
    for i in range(0, 244, 16):
        hex_str = data[i:min(i+16, 244)].hex().upper()
        hex_fmt = " ".join([hex_str[j:j+2] for j in range(0, len(hex_str), 2)])
        print(f"  {i:3d}: {hex_fmt}")

except Exception as e:
    print(f"读取 DB10 失败: {e}")
    import traceback
    traceback.print_exc()

client.disconnect()
print()
print("=" * 100)
print("读取完成")
print("=" * 100)
input("按回车键退出...")

