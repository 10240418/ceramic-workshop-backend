# -*- coding: utf-8 -*-
"""
DB8 (料仓设备) 数据块解析 - 独立脚本
包含 9 个料仓: 4短+2无+3长
应用数据转换: 称重×0.1, 温度×0.1, 电流×0.001×20, 功率×0.0001×20, 能耗×2
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
print("DB8 (料仓设备) 数据块解析")
print(f"PLC: {PLC_IP}  Rack: {PLC_RACK}  Slot: {PLC_SLOT}")
print("=" * 100)

try:
    data = client.db_read(8, 0, 626)
    data = bytes(data)

    print()
    print("--- 短料仓 (4个) - 有称重 ---")
    print()

    # 短料仓配置: [(offset, name, ui_name)]
    short_hoppers = [
        (0, "short_hopper_1", "7号窑"),
        (72, "short_hopper_3", "5号窑"),
        (144, "short_hopper_2", "6号窑"),
        (216, "short_hopper_4", "4号窑"),
    ]

    for offset, device_id, ui_name in short_hoppers:
        # 称重传感器 (14字节)
        weight_raw = struct.unpack(">f", data[offset:offset+4])[0]
        feed_rate_raw = struct.unpack(">f", data[offset+4:offset+8])[0]
        total_weight_raw = struct.unpack(">f", data[offset+10:offset+14])[0]
        
        weight = weight_raw * 0.1
        feed_rate = feed_rate_raw * 0.1
        total_weight = total_weight_raw * 0.1
        
        # 温度传感器 (2字节)
        temp_raw = struct.unpack(">h", data[offset+14:offset+16])[0]
        temp = temp_raw * 0.1
        
        # 电表 (56字节, offset+16开始)
        meter_offset = offset + 16
        pt_raw = struct.unpack(">f", data[meter_offset+40:meter_offset+44])[0]
        impe_raw = struct.unpack(">f", data[meter_offset+52:meter_offset+56])[0]
        ua_raw = struct.unpack(">f", data[meter_offset+4:meter_offset+8])[0]
        i0_raw = struct.unpack(">f", data[meter_offset+16:meter_offset+20])[0]
        i1_raw = struct.unpack(">f", data[meter_offset+20:meter_offset+24])[0]
        i2_raw = struct.unpack(">f", data[meter_offset+24:meter_offset+28])[0]
        
        # 应用转换公式 (料仓电流变比=20)
        pt = pt_raw * 0.0001 * 20
        impe = impe_raw * 2
        ua = ua_raw * 0.1
        i0 = i0_raw * 0.001 * 20
        i1 = i1_raw * 0.001 * 20
        i2 = i2_raw * 0.001 * 20
        
        print(f"[{device_id}] {ui_name}")
        print(f"  称重: 当前={weight:.1f}kg, 投料速率={feed_rate:.1f}kg/h, 累计={total_weight:.1f}kg")
        print(f"  温度: {temp:.1f}°C")
        print(f"  电表: 功率={pt:.2f}kW, 能耗={impe:.1f}kWh, 电压={ua:.1f}V")
        print(f"        电流: A相={i0:.1f}A, B相={i1:.1f}A, C相={i2:.1f}A")
        print()

    print()
    print("--- 无料仓 (2个) - 无称重 ---")
    print()

    # 无料仓配置
    no_hoppers = [
        (288, "no_hopper_1", "2号窑"),
        (346, "no_hopper_2", "1号窑"),
    ]

    for offset, device_id, ui_name in no_hoppers:
        # 温度传感器 (2字节)
        temp_raw = struct.unpack(">h", data[offset:offset+2])[0]
        temp = temp_raw * 0.1
        
        # 电表 (56字节, offset+2开始)
        meter_offset = offset + 2
        pt_raw = struct.unpack(">f", data[meter_offset+40:meter_offset+44])[0]
        impe_raw = struct.unpack(">f", data[meter_offset+52:meter_offset+56])[0]
        ua_raw = struct.unpack(">f", data[meter_offset+4:meter_offset+8])[0]
        i0_raw = struct.unpack(">f", data[meter_offset+16:meter_offset+20])[0]
        i1_raw = struct.unpack(">f", data[meter_offset+20:meter_offset+24])[0]
        i2_raw = struct.unpack(">f", data[meter_offset+24:meter_offset+28])[0]
        
        # 应用转换公式
        pt = pt_raw * 0.0001 * 20
        impe = impe_raw * 2
        ua = ua_raw * 0.1
        i0 = i0_raw * 0.001 * 20
        i1 = i1_raw * 0.001 * 20
        i2 = i2_raw * 0.001 * 20
        
        print(f"[{device_id}] {ui_name}")
        print(f"  温度: {temp:.1f}°C")
        print(f"  电表: 功率={pt:.2f}kW, 能耗={impe:.1f}kWh, 电压={ua:.1f}V")
        print(f"        电流: A相={i0:.1f}A, B相={i1:.1f}A, C相={i2:.1f}A")
        print()

    print()
    print("--- 长料仓 (3个) - 有称重+双温度 ---")
    print()

    # 长料仓配置
    long_hoppers = [
        (404, "long_hopper_1", "8号窑"),
        (478, "long_hopper_2", "3号窑"),
        (552, "long_hopper_3", "9号窑"),
    ]

    for offset, device_id, ui_name in long_hoppers:
        # 称重传感器 (14字节)
        weight_raw = struct.unpack(">f", data[offset:offset+4])[0]
        feed_rate_raw = struct.unpack(">f", data[offset+4:offset+8])[0]
        total_weight_raw = struct.unpack(">f", data[offset+10:offset+14])[0]
        
        weight = weight_raw * 0.1
        feed_rate = feed_rate_raw * 0.1
        total_weight = total_weight_raw * 0.1
        
        # 温度传感器1 (2字节)
        temp1_raw = struct.unpack(">h", data[offset+14:offset+16])[0]
        temp1 = temp1_raw * 0.1
        
        # 温度传感器2 (2字节)
        temp2_raw = struct.unpack(">h", data[offset+16:offset+18])[0]
        temp2 = temp2_raw * 0.1
        
        # 电表 (56字节, offset+18开始)
        meter_offset = offset + 18
        pt_raw = struct.unpack(">f", data[meter_offset+40:meter_offset+44])[0]
        impe_raw = struct.unpack(">f", data[meter_offset+52:meter_offset+56])[0]
        ua_raw = struct.unpack(">f", data[meter_offset+4:meter_offset+8])[0]
        i0_raw = struct.unpack(">f", data[meter_offset+16:meter_offset+20])[0]
        i1_raw = struct.unpack(">f", data[meter_offset+20:meter_offset+24])[0]
        i2_raw = struct.unpack(">f", data[meter_offset+24:meter_offset+28])[0]
        
        # 应用转换公式
        pt = pt_raw * 0.0001 * 20
        impe = impe_raw * 2
        ua = ua_raw * 0.1
        i0 = i0_raw * 0.001 * 20
        i1 = i1_raw * 0.001 * 20
        i2 = i2_raw * 0.001 * 20
        
        print(f"[{device_id}] {ui_name}")
        print(f"  称重: 当前={weight:.1f}kg, 投料速率={feed_rate:.1f}kg/h, 累计={total_weight:.1f}kg")
        print(f"  温度: 上部={temp1:.1f}°C, 下部={temp2:.1f}°C")
        print(f"  电表: 功率={pt:.2f}kW, 能耗={impe:.1f}kWh, 电压={ua:.1f}V")
        print(f"        电流: A相={i0:.1f}A, B相={i1:.1f}A, C相={i2:.1f}A")
        print()

    print()
    print("--- 原始数据 (每行16字节) ---")
    for i in range(0, 626, 16):
        hex_str = data[i:min(i+16, 626)].hex().upper()
        hex_fmt = " ".join([hex_str[j:j+2] for j in range(0, len(hex_str), 2)])
        print(f"  {i:3d}: {hex_fmt}")

except Exception as e:
    print(f"读取 DB8 失败: {e}")
    import traceback
    traceback.print_exc()

client.disconnect()
print()
print("=" * 100)
print("读取完成")
print("=" * 100)
input("按回车键退出...")

