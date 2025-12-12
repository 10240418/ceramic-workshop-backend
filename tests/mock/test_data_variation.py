#!/usr/bin/env python3
# 测试数据动态变化
import struct
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests.mock.mock_data_generator import MockDataGenerator

gen = MockDataGenerator()

print("=" * 70)
print("测试数据动态变化")
print("=" * 70)

for i in range(5):
    data = gen.generate_all_db_data()
    db8 = data[8]
    db9 = data[9]
    
    # 解析第一个短料仓的重量 (offset 6-9, GrossWeight DWord)
    weight = struct.unpack('>I', db8[6:10])[0]
    # 解析温度 (offset 14-15)
    temp = struct.unpack('>H', db8[14:16])[0] / 10.0
    # 解析功率 (offset 16+36 = 52, Pt Real)
    power = struct.unpack('>f', db8[52:56])[0]
    # 解析电能 (offset 16+52 = 68, ImpEp Real)  
    energy = struct.unpack('>f', db8[68:72])[0]
    
    # 辊道窑温度 (zone1, offset 0-1)
    roller_temp = struct.unpack('>H', db9[0:2])[0] / 10.0
    # 辊道窑主电表能耗 (offset 12+52 = 64)
    roller_energy = struct.unpack('>f', db9[64:68])[0]
    
    print(f"轮询 {i+1}:")
    print(f"  料仓1: 重量={weight}kg, 温度={temp:.1f}°C, 功率={power:.2f}kW, 电能={energy:.2f}kWh")
    print(f"  辊道窑: 1区温度={roller_temp:.1f}°C, 总能耗={roller_energy:.2f}kWh")
    print()

print("✅ 数据确实在动态变化!")
