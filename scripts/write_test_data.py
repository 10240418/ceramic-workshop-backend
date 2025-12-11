#!/usr/bin/env python3
# ============================================================
# 写入测试数据到 InfluxDB
# ============================================================
# 功能: 为所有配置的模块生成模拟数据并写入数据库
# 使用: python3 scripts/write_test_data.py
# ============================================================

import sys
from pathlib import Path
from datetime import datetime, timedelta
import random

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from influxdb_client import Point
from app.core.influxdb import get_influx_client, write_points
from config import get_settings

settings = get_settings()


def generate_weigh_sensor_data(device_id: int, device_type: str, timestamp: datetime) -> Point:
    """生成称重传感器数据"""
    return (Point("module_data")
        .tag("device_id", str(device_id))
        .tag("device_type", device_type)
        .tag("module_name", "WeighSensor")
        .tag("sensor_type", "hopper_weight")
        .field("BaseWeigh_GrossWeigh", float(random.randint(800, 1200)))
        .field("BaseWeigh_NetWeigh", float(random.randint(750, 1150)))
        .field("StatusWord", float(random.randint(0, 100)))
        .field("AdvWeigh_GrossWeigh", float(random.randint(80000, 120000)))
        .field("AdvWeigh_NetWeigh", float(random.randint(75000, 115000)))
        .time(timestamp))


def generate_flow_meter_data(device_id: int, device_type: str, timestamp: datetime) -> Point:
    """生成流量计数据"""
    return (Point("module_data")
        .tag("device_id", str(device_id))
        .tag("device_type", device_type)
        .tag("module_name", "FlowMeter")
        .tag("sensor_type", "material_flow")
        .field("RtFlow", float(random.randint(50, 150)))
        .field("TotalFlow", float(random.randint(10000, 50000)))
        .field("TotalFlowMilli", float(random.randint(0, 999)))
        .time(timestamp))


def generate_modbus_devkit_data(device_id: int, device_type: str, timestamp: datetime) -> Point:
    """生成Modbus设备数据"""
    return (Point("module_data")
        .tag("device_id", str(device_id))
        .tag("device_type", device_type)
        .tag("module_name", "ModbusDevKit")
        .tag("sensor_type", "voltage_current")
        .field("VoltageCH1", round(random.uniform(220, 240), 1))
        .field("VoltageCH2", round(random.uniform(220, 240), 1))
        .field("AmpereCH1", round(random.uniform(10, 30), 1))
        .field("AmpereCH2", round(random.uniform(10, 30), 1))
        .time(timestamp))


def generate_water_meter_data(device_id: int, device_type: str, timestamp: datetime) -> Point:
    """生成水表数据"""
    return (Point("module_data")
        .tag("device_id", str(device_id))
        .tag("device_type", device_type)
        .tag("module_name", "WaterMeter")
        .tag("sensor_type", "cooling_water")
        .field("Flow", float(random.randint(100, 500)))
        .field("Total_Flow", float(random.randint(50000, 200000)))
        .time(timestamp))


def generate_electricity_meter_data(device_id: int, device_type: str, timestamp: datetime) -> Point:
    """生成电参数据"""
    return (Point("module_data")
        .tag("device_id", str(device_id))
        .tag("device_type", device_type)
        .tag("module_name", "ElectricityMeter")
        .tag("sensor_type", "power_meter")
        .field("Uab_0", round(random.uniform(380, 400), 2))
        .field("Uab_1", round(random.uniform(380, 400), 2))
        .field("Uab_2", round(random.uniform(380, 400), 2))
        .field("Ua_0", round(random.uniform(220, 240), 2))
        .field("Ua_1", round(random.uniform(220, 240), 2))
        .field("Ua_2", round(random.uniform(220, 240), 2))
        .field("I_0", round(random.uniform(50, 150), 2))
        .field("I_1", round(random.uniform(50, 150), 2))
        .field("I_2", round(random.uniform(50, 150), 2))
        .field("Pt", round(random.uniform(30, 80), 2))
        .time(timestamp))


def write_historical_data(hours: int = 2):
    """写入历史数据"""
    print("=" * 70)
    print("🚀 开始写入测试数据到 InfluxDB")
    print("=" * 70)
    
    # 生成过去N小时的数据
    now = datetime.utcnow()
    points = []
    
    print(f"\n📊 生成过去 {hours} 小时的模拟数据...")
    
    # 每5分钟一个数据点
    intervals = hours * 12  # 每小时12个点
    
    for i in range(intervals):
        timestamp = now - timedelta(minutes=5 * (intervals - i))
        
        # 测试设备1 - 所有模块
        points.append(generate_weigh_sensor_data(1, "test_device", timestamp))
        points.append(generate_flow_meter_data(1, "test_device", timestamp))
        points.append(generate_modbus_devkit_data(1, "test_device", timestamp))
        points.append(generate_water_meter_data(1, "test_device", timestamp))
        points.append(generate_electricity_meter_data(1, "test_device", timestamp))
        
        # 回转窑1号 - 3个模块
        points.append(generate_weigh_sensor_data(1, "rotary_kiln", timestamp))
        points.append(generate_flow_meter_data(1, "rotary_kiln", timestamp))
        points.append(generate_electricity_meter_data(1, "rotary_kiln", timestamp))
        
        # 回转窑2号 - 1个模块
        points.append(generate_weigh_sensor_data(2, "rotary_kiln", timestamp))
        
        # 回转窑3号 - 1个模块
        points.append(generate_water_meter_data(3, "rotary_kiln", timestamp))
        
        # 辊道窑1号 - 1个模块
        points.append(generate_electricity_meter_data(1, "roller_kiln", timestamp))
        
        # SCR设备1号 - 2个模块
        points.append(generate_modbus_devkit_data(1, "scr", timestamp))
        points.append(generate_flow_meter_data(1, "scr", timestamp))
        
        # SCR设备2号 - 1个模块
        points.append(generate_flow_meter_data(2, "scr", timestamp))
    
    print(f"  ✅ 生成了 {len(points)} 个数据点")
    
    # 批量写入
    print(f"\n💾 写入数据到 InfluxDB...")
    batch_size = 500
    total_batches = (len(points) + batch_size - 1) // batch_size
    
    for i in range(0, len(points), batch_size):
        batch = points[i:i + batch_size]
        write_points(batch)
        current_batch = i // batch_size + 1
        print(f"  ✓ 批次 {current_batch}/{total_batches} 完成 ({len(batch)} 个点)")
    
    print(f"\n✅ 测试数据写入完成！")
    print(f"\n📋 数据统计:")
    print(f"  • 时间范围: {hours} 小时")
    print(f"  • 数据点数: {len(points)}")
    print(f"  • 设备数量: 8 个")
    print(f"  • 模块数量: 15 个实例")
    print("=" * 70)
    
    return len(points)


def write_realtime_data():
    """写入当前时刻的实时数据"""
    print("\n🔄 写入实时数据...")
    
    now = datetime.utcnow()
    points = []
    
    # 测试设备1 - 所有模块
    points.append(generate_weigh_sensor_data(1, "test_device", now))
    points.append(generate_flow_meter_data(1, "test_device", now))
    points.append(generate_modbus_devkit_data(1, "test_device", now))
    points.append(generate_water_meter_data(1, "test_device", now))
    points.append(generate_electricity_meter_data(1, "test_device", now))
    
    # 回转窑设备
    points.append(generate_weigh_sensor_data(1, "rotary_kiln", now))
    points.append(generate_flow_meter_data(1, "rotary_kiln", now))
    points.append(generate_electricity_meter_data(1, "rotary_kiln", now))
    points.append(generate_weigh_sensor_data(2, "rotary_kiln", now))
    points.append(generate_water_meter_data(3, "rotary_kiln", now))
    
    # 辊道窑设备
    points.append(generate_electricity_meter_data(1, "roller_kiln", now))
    
    # SCR设备
    points.append(generate_modbus_devkit_data(1, "scr", now))
    points.append(generate_flow_meter_data(1, "scr", now))
    points.append(generate_flow_meter_data(2, "scr", now))
    
    write_points(points)
    print(f"  ✅ 写入 {len(points)} 个实时数据点")


if __name__ == "__main__":
    try:
        # 写入历史数据（过去2小时）
        total_points = write_historical_data(hours=2)
        
        # 写入实时数据
        write_realtime_data()
        
        print("\n🎉 所有测试数据写入成功！")
        print("\n💡 提示:")
        print("  • 访问 http://localhost:8086 查看 InfluxDB 数据")
        print("  • 使用 Data Explorer 查询 module_data 表")
        print("  • 启动后端服务测试 API 接口")
        
    except Exception as e:
        print(f"\n❌ 写入失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
