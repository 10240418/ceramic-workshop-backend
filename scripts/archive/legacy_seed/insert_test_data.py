#!/usr/bin/env python3
# ============================================================
# 脚本说明: insert_test_data.py - 手动插入测试数据
# ============================================================
# 用途: 绕过 PLC,直接向 InfluxDB 插入当前时间的测试数据
# 使用: python scripts/insert_test_data.py
# ============================================================

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import random
from datetime import datetime, timezone
from app.core.influxdb import write_point


def insert_test_data():
    """插入当前时间的测试数据到 InfluxDB"""
    print("=" * 70)
    print(" 开始插入测试数据到 InfluxDB")
    print("=" * 70)
    
    current_time = datetime.now(timezone.utc)
    print(f"\n⏰ 插入时间: {current_time.isoformat()}\n")
    
    try:
        # 1. 插入料仓数据 (9个)
        print("📦 插入料仓数据...")
        insert_hopper_data()
        
        # 2. 插入辊道窑数据 (6温区)
        print(" 插入辊道窑数据...")
        insert_roller_kiln_data()
        
        # 3. 插入SCR设备数据 (2台)
        print("⚙️  插入SCR设备数据...")
        insert_scr_data()
        
        # 4. 插入风机数据 (2台)
        print("🌀 插入风机数据...")
        insert_fan_data()
        
        print("\n" + "=" * 70)
        print("[正确] 测试数据插入完成！")
        print("=" * 70)
        print("\n 提示: 现在可以调用 API 查询数据了:")
        print("  - GET /api/hopper/realtime/batch")
        print("  - GET /api/roller/realtime/formatted")
        print("  - GET /api/scr-fan/realtime/batch")
        print("\n")
        return True
        
    except Exception as e:
        print(f"\n[错误] 错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def insert_hopper_data():
    """插入9个料仓的测试数据（按配置文件结构）"""
    # 短料仓 (4个): WeighSensor(weight) + TemperatureSensor(temp) + ElectricityMeter(meter)
    short_hoppers = [
        "short_hopper_1", "short_hopper_2", "short_hopper_3", "short_hopper_4"
    ]
    
    for device_id in short_hoppers:
        # 电表数据
        write_point(
            measurement="sensor_data",
            tags={
                "device_id": device_id,
                "device_type": "short_hopper",
                "module_type": "ElectricityMeter",
                "module_tag": "meter",
                "db_number": "8"
            },
            fields={
                "Pt": round(random.uniform(50, 150), 2),
                "ImpEp": round(random.uniform(2000, 5000), 2),
                "Ua_0": round(random.uniform(220, 240), 2),
                "Ua_1": round(random.uniform(220, 240), 2),
                "Ua_2": round(random.uniform(220, 240), 2),
                "I_0": round(random.uniform(10, 30), 2),
                "I_1": round(random.uniform(10, 30), 2),
                "I_2": round(random.uniform(10, 30), 2),
            }
        )
        
        # 温度数据
        write_point(
            measurement="sensor_data",
            tags={
                "device_id": device_id,
                "device_type": "short_hopper",
                "module_type": "TemperatureSensor",
                "module_tag": "temp",
                "db_number": "8"
            },
            fields={
                "temperature": round(random.uniform(20, 80), 2),
            }
        )
        
        # 称重数据
        write_point(
            measurement="sensor_data",
            tags={
                "device_id": device_id,
                "device_type": "short_hopper",
                "module_type": "WeighSensor",
                "module_tag": "weight",
                "db_number": "8"
            },
            fields={
                "weight": round(random.uniform(500, 2000), 2),
                "feed_rate": round(random.uniform(10, 50), 2),
            }
        )
        
        print(f"  ✓ {device_id}: 电表(meter) + 温度(temp) + 称重(weight)")
    
    # 无料仓 (2个): TemperatureSensor(temp) + ElectricityMeter(meter)
    no_hoppers = ["no_hopper_1", "no_hopper_2"]
    
    for device_id in no_hoppers:
        # 电表数据
        write_point(
            measurement="sensor_data",
            tags={
                "device_id": device_id,
                "device_type": "no_hopper",
                "module_type": "ElectricityMeter",
                "module_tag": "meter",
                "db_number": "8"
            },
            fields={
                "Pt": round(random.uniform(50, 150), 2),
                "ImpEp": round(random.uniform(1000, 5000), 2),
                "Ua_0": round(random.uniform(220, 240), 2),
                "Ua_1": round(random.uniform(220, 240), 2),
                "Ua_2": round(random.uniform(220, 240), 2),
                "I_0": round(random.uniform(10, 30), 2),
                "I_1": round(random.uniform(10, 30), 2),
                "I_2": round(random.uniform(10, 30), 2),
            }
        )
        
        # 温度数据
        write_point(
            measurement="sensor_data",
            tags={
                "device_id": device_id,
                "device_type": "no_hopper",
                "module_type": "TemperatureSensor",
                "module_tag": "temp",
                "db_number": "8"
            },
            fields={
                "temperature": round(random.uniform(20, 80), 2),
            }
        )
        
        # 无料仓也有称重（看你之前的数据）
        write_point(
            measurement="sensor_data",
            tags={
                "device_id": device_id,
                "device_type": "no_hopper",
                "module_type": "WeighSensor",
                "module_tag": "weight",
                "db_number": "8"
            },
            fields={
                "weight": round(random.uniform(1000, 2000), 2),
                "feed_rate": round(random.uniform(10, 20), 2),
            }
        )
        
        print(f"  ✓ {device_id}: 电表(meter) + 温度(temp) + 称重(weight)")
    
    # 长料仓 (3个): WeighSensor(weight) + TemperatureSensor(temp1) + TemperatureSensor(temp2) + ElectricityMeter(meter)
    long_hoppers = ["long_hopper_1", "long_hopper_2", "long_hopper_3"]
    
    for device_id in long_hoppers:
        # 电表数据
        write_point(
            measurement="sensor_data",
            tags={
                "device_id": device_id,
                "device_type": "long_hopper",
                "module_type": "ElectricityMeter",
                "module_tag": "meter",
                "db_number": "8"
            },
            fields={
                "Pt": round(random.uniform(50, 150), 2),
                "ImpEp": round(random.uniform(2000, 5000), 2),
                "Ua_0": round(random.uniform(220, 240), 2),
                "Ua_1": round(random.uniform(220, 240), 2),
                "Ua_2": round(random.uniform(220, 240), 2),
                "I_0": round(random.uniform(10, 30), 2),
                "I_1": round(random.uniform(10, 30), 2),
                "I_2": round(random.uniform(10, 30), 2),
            }
        )
        
        # 温度数据1
        write_point(
            measurement="sensor_data",
            tags={
                "device_id": device_id,
                "device_type": "long_hopper",
                "module_type": "TemperatureSensor",
                "module_tag": "temp1",
                "db_number": "8"
            },
            fields={
                "temperature": round(random.uniform(20, 80), 2),
            }
        )
        
        # 温度数据2
        write_point(
            measurement="sensor_data",
            tags={
                "device_id": device_id,
                "device_type": "long_hopper",
                "module_type": "TemperatureSensor",
                "module_tag": "temp2",
                "db_number": "8"
            },
            fields={
                "temperature": round(random.uniform(20, 80), 2),
            }
        )
        
        # 称重数据
        write_point(
            measurement="sensor_data",
            tags={
                "device_id": device_id,
                "device_type": "long_hopper",
                "module_type": "WeighSensor",
                "module_tag": "weight",
                "db_number": "8"
            },
            fields={
                "weight": round(random.uniform(500, 2000), 2),
                "feed_rate": round(random.uniform(20, 40), 2),
            }
        )
        
        print(f"  ✓ {device_id}: 电表(meter) + 温度1(temp1) + 温度2(temp2) + 称重(weight)")
    
    print(f"  [正确] 完成 {len(short_hoppers) + len(no_hoppers) + len(long_hoppers)} 个料仓")


def insert_roller_kiln_data():
    """插入辊道窑6个温区的测试数据"""
    zones = ["zone1", "zone2", "zone3", "zone4", "zone5", "zone6"]
    
    for zone in zones:
        # 电表数据
        write_point(
            measurement="sensor_data",
            tags={
                "device_id": "roller_kiln_1",
                "device_type": "roller_kiln",
                "module_type": "ElectricityMeter",
                "module_tag": zone,
                "db_number": "9"
            },
            fields={
                "Pt": round(random.uniform(150, 280), 2),
                "ImpEp": round(random.uniform(8000, 14000), 2),
                "Ua_0": round(random.uniform(220, 238), 2),
                "Ua_1": round(random.uniform(220, 238), 2),
                "Ua_2": round(random.uniform(220, 238), 2),
                "I_0": round(random.uniform(25, 45), 2),
                "I_1": round(random.uniform(25, 45), 2),
                "I_2": round(random.uniform(25, 45), 2),
            }
        )
        
        # 温度数据
        write_point(
            measurement="sensor_data",
            tags={
                "device_id": "roller_kiln_1",
                "device_type": "roller_kiln",
                "module_type": "TemperatureSensor",
                "module_tag": zone,
                "db_number": "9"
            },
            fields={
                "temperature": round(random.uniform(850, 1150), 2),
            }
        )
        
        print(f"  ✓ {zone}: 电表+温度")
    
    print(f"  [正确] 完成辊道窑 {len(zones)} 个温区")


def insert_scr_data():
    """插入2台SCR设备的测试数据"""
    scr_devices = ["scr_1", "scr_2"]
    
    for device_id in scr_devices:
        # 电表数据
        write_point(
            measurement="sensor_data",
            tags={
                "device_id": device_id,
                "device_type": "scr",
                "module_type": "ElectricityMeter",
                "module_tag": "elec",
                "db_number": "10"
            },
            fields={
                "Pt": round(random.uniform(90, 180), 2),
                "ImpEp": round(random.uniform(3000, 7000), 2),
                "Ua_0": round(random.uniform(220, 235), 2),
                "Ua_1": round(random.uniform(220, 235), 2),
                "Ua_2": round(random.uniform(220, 235), 2),
                "I_0": round(random.uniform(18, 32), 2),
                "I_1": round(random.uniform(18, 32), 2),
                "I_2": round(random.uniform(18, 32), 2),
            }
        )
        
        # 燃气流量数据
        write_point(
            measurement="sensor_data",
            tags={
                "device_id": device_id,
                "device_type": "scr",
                "module_type": "GasMeter",
                "module_tag": "gas",
                "db_number": "10"
            },
            fields={
                "flow_rate": round(random.uniform(60, 140), 2),
                "total_flow": round(random.uniform(15000, 45000), 2),
            }
        )
        
        print(f"  ✓ {device_id}: 电表+燃气表")
    
    print(f"  [正确] 完成 {len(scr_devices)} 台SCR设备")


def insert_fan_data():
    """插入2台风机的测试数据"""
    fan_devices = ["fan_1", "fan_2"]
    
    for device_id in fan_devices:
        # 电表数据
        write_point(
            measurement="sensor_data",
            tags={
                "device_id": device_id,
                "device_type": "fan",
                "module_type": "ElectricityMeter",
                "module_tag": "elec",
                "db_number": "10"
            },
            fields={
                "Pt": round(random.uniform(40, 90), 2),
                "ImpEp": round(random.uniform(800, 2500), 2),
                "Ua_0": round(random.uniform(220, 235), 2),
                "Ua_1": round(random.uniform(220, 235), 2),
                "Ua_2": round(random.uniform(220, 235), 2),
                "I_0": round(random.uniform(8, 18), 2),
                "I_1": round(random.uniform(8, 18), 2),
                "I_2": round(random.uniform(8, 18), 2),
            }
        )
        
        print(f"  ✓ {device_id}: 电表")
    
    print(f"  [正确] 完成 {len(fan_devices)} 台风机")


if __name__ == "__main__":
    insert_test_data()
