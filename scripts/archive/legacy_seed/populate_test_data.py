#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试数据填充脚本
用途：向InfluxDB填充模拟的历史数据，用于测试导出功能
"""

from datetime import datetime, timedelta, timezone
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
import random

# InfluxDB配置
INFLUX_URL = "http://localhost:8086"
INFLUX_TOKEN = "ceramic-workshop-token"
INFLUX_ORG = "ceramic-workshop"
INFLUX_BUCKET = "sensor_data"

def populate_electricity_data():
    """填充电量数据（所有设备）"""
    print("=" * 80)
    print("1. 填充电量数据")
    print("=" * 80)
    
    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    write_api = client.write_api(write_options=SYNCHRONOUS)
    
    # 设备列表
    devices = [
        # 料仓（9个）
        ("short_hopper_1", "hopper", 15.0, 30.0),
        ("short_hopper_2", "hopper", 15.0, 30.0),
        ("short_hopper_3", "hopper", 15.0, 30.0),
        ("short_hopper_4", "hopper", 15.0, 30.0),
        ("no_hopper_1", "hopper", 15.0, 30.0),
        ("no_hopper_2", "hopper", 15.0, 30.0),
        ("long_hopper_1", "hopper", 15.0, 30.0),
        ("long_hopper_2", "hopper", 15.0, 30.0),
        ("long_hopper_3", "hopper", 15.0, 30.0),
        # 辊道窑温区（6个）
        ("zone1", "roller_kiln_zone", 20.0, 50.0),
        ("zone2", "roller_kiln_zone", 20.0, 50.0),
        ("zone3", "roller_kiln_zone", 20.0, 50.0),
        ("zone4", "roller_kiln_zone", 20.0, 50.0),
        ("zone5", "roller_kiln_zone", 20.0, 50.0),
        ("zone6", "roller_kiln_zone", 20.0, 50.0),
        # 辊道窑总表（1个）
        ("roller_kiln_total", "roller_kiln_total", 120.0, 300.0),
        # SCR燃气表（2个）
        ("scr_1", "scr", 10.0, 25.0),
        ("scr_2", "scr", 10.0, 25.0),
        # SCR氨水泵（2个）
        ("scr_1_pump", "scr_pump", 5.0, 15.0),
        ("scr_2_pump", "scr_pump", 5.0, 15.0),
        # 风机（2个）
        ("fan_1", "fan", 8.0, 20.0),
        ("fan_2", "fan", 8.0, 20.0),
    ]
    
    # 生成最近3天的数据
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=3)
    
    total_points = 0
    
    for device_id, device_type, min_power, max_power in devices:
        print(f"\n  处理设备: {device_id} ({device_type})")
        
        # 初始电量读数（随机10000-50000 kWh）
        base_energy = random.uniform(10000.0, 50000.0)
        
        points = []
        
        # 每6秒生成一个数据点
        current_time = start_time
        point_count = 0
        
        while current_time <= end_time:
            # 模拟功率（在min_power和max_power之间波动）
            power = random.uniform(min_power, max_power)
            
            # 累计电量（每6秒增加 power * 6 / 3600 kWh）
            energy_increment = power * 6 / 3600
            base_energy += energy_increment
            
            # 创建数据点
            point = Point("sensor_data") \
                .tag("device_id", device_id) \
                .tag("device_type", device_type) \
                .tag("module_type", "ElectricityMeter") \
                .tag("module_tag", "elec_meter") \
                .field("Pt", power) \
                .field("ImpEp", base_energy) \
                .time(current_time)
            
            points.append(point)
            point_count += 1
            
            # 每1000个点写入一次
            if len(points) >= 1000:
                write_api.write(bucket=INFLUX_BUCKET, record=points)
                points = []
            
            current_time += timedelta(seconds=6)
        
        # 写入剩余数据
        if points:
            write_api.write(bucket=INFLUX_BUCKET, record=points)
        
        total_points += point_count
        print(f"    已写入 {point_count} 个数据点")
    
    client.close()
    print(f"\n[OK] 电量数据填充完成！总计 {total_points} 个数据点")
    return total_points


def populate_gas_data():
    """填充燃气数据（仅SCR设备）"""
    print("\n" + "=" * 80)
    print("2. 填充燃气数据")
    print("=" * 80)
    
    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    write_api = client.write_api(write_options=SYNCHRONOUS)
    
    # SCR设备
    devices = [
        ("scr_1", "scr", 5.0, 15.0),
        ("scr_2", "scr", 5.0, 15.0)
    ]
    
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=3)
    
    total_points = 0
    
    for device_id, device_type, min_flow, max_flow in devices:
        print(f"\n  处理设备: {device_id}")
        
        # 初始累计流量（随机5000-10000 m³）
        base_flow = random.uniform(5000.0, 10000.0)
        
        points = []
        
        current_time = start_time
        point_count = 0
        
        while current_time <= end_time:
            # 模拟流量（5-15 m³/h）
            flow_rate = random.uniform(min_flow, max_flow)
            
            # 累计流量（每6秒增加 flow_rate * 6 / 3600 m³）
            flow_increment = flow_rate * 6 / 3600
            base_flow += flow_increment
            
            point = Point("sensor_data") \
                .tag("device_id", device_id) \
                .tag("device_type", device_type) \
                .tag("module_type", "GasMeter") \
                .tag("module_tag", "gas_meter") \
                .field("flow_rate", flow_rate) \
                .field("total_flow", base_flow) \
                .time(current_time)
            
            points.append(point)
            point_count += 1
            
            if len(points) >= 1000:
                write_api.write(bucket=INFLUX_BUCKET, record=points)
                points = []
            
            current_time += timedelta(seconds=6)
        
        if points:
            write_api.write(bucket=INFLUX_BUCKET, record=points)
        
        total_points += point_count
        print(f"    已写入 {point_count} 个数据点")
    
    client.close()
    print(f"\n[OK] 燃气数据填充完成！总计 {total_points} 个数据点")
    return total_points


def populate_feeding_data():
    """填充投料数据（仅有料仓的设备）"""
    print("\n" + "=" * 80)
    print("3. 填充投料数据")
    print("=" * 80)
    
    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    write_api = client.write_api(write_options=SYNCHRONOUS)
    
    # 有投料的料仓（7个，no_hopper_1和no_hopper_2没有料仓）
    hoppers = [
        "short_hopper_1", "short_hopper_2", "short_hopper_3", "short_hopper_4",
        "long_hopper_1", "long_hopper_2", "long_hopper_3"
    ]
    
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=3)
    
    total_points = 0
    
    for device_id in hoppers:
        print(f"\n  处理设备: {device_id}")
        
        points = []
        
        # 每小时生成一次投料记录
        current_time = start_time
        point_count = 0
        
        while current_time <= end_time:
            # 模拟投料量（50-150 kg）
            added_weight = random.uniform(50.0, 150.0)
            
            point = Point("feeding_records") \
                .tag("device_id", device_id) \
                .tag("device_type", "hopper") \
                .field("added_weight", added_weight) \
                .time(current_time)
            
            points.append(point)
            point_count += 1
            
            if len(points) >= 100:
                write_api.write(bucket=INFLUX_BUCKET, record=points)
                points = []
            
            current_time += timedelta(hours=1)
        
        if points:
            write_api.write(bucket=INFLUX_BUCKET, record=points)
        
        total_points += point_count
        print(f"    已写入 {point_count} 个投料记录")
    
    client.close()
    print(f"\n[OK] 投料数据填充完成！总计 {total_points} 个记录")
    return total_points


def main():
    """主函数"""
    print("\n" + "=" * 80)
    print("开始填充测试数据到 InfluxDB")
    print("=" * 80)
    print(f"目标: {INFLUX_URL}")
    print(f"Bucket: {INFLUX_BUCKET}")
    print(f"时间范围: 最近3天")
    print("=" * 80)
    
    try:
        # 1. 填充电量数据
        electricity_points = populate_electricity_data()
        
        # 2. 填充燃气数据
        gas_points = populate_gas_data()
        
        # 3. 填充投料数据
        feeding_points = populate_feeding_data()
        
        # 总结
        print("\n" + "=" * 80)
        print("[OK] 所有测试数据填充完成！")
        print("=" * 80)
        print(f"电量数据点: {electricity_points}")
        print(f"燃气数据点: {gas_points}")
        print(f"投料记录: {feeding_points}")
        print(f"总计: {electricity_points + gas_points + feeding_points}")
        print("=" * 80)
        
        print("\n现在可以测试导出功能了:")
        print("  python scripts/test_export_apis_complete.py")
        
        return True
        
    except Exception as e:
        print(f"\n[ERROR] 填充数据失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)

