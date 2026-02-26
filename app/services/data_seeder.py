# ============================================================
# 文件说明: data_seeder.py - 数据初始化服务
# ============================================================
# 功能: 启动时自动插入模拟数据，确保 list 接口永远不为空
# ============================================================

import random
from datetime import datetime, timedelta
from app.core.influxdb import write_point


def seed_mock_data():
    """插入模拟数据到 InfluxDB，确保所有设备都有初始数据"""
    print(" 开始插入模拟数据...")
    
    try:
        # 1. 料仓数据 (9个料仓)
        seed_hopper_data()
        
        # 2. 辊道窑数据 (6个温区)
        seed_roller_kiln_data()
        
        # 3. SCR设备数据 (2台)
        seed_scr_data()
        
        # 4. 风机数据 (2台)
        seed_fan_data()
        
        print("[OK] 模拟数据插入完成！")
        return True
    except Exception as e:
        print(f"[ERROR] 模拟数据插入失败: {str(e)}")
        return False


def seed_hopper_data():
    """插入料仓模拟数据"""
    hoppers = [
        # 短料仓 (4个)
        {"device_id": "short_hopper_1", "device_type": "short_hopper"},
        {"device_id": "short_hopper_2", "device_type": "short_hopper"},
        {"device_id": "short_hopper_3", "device_type": "short_hopper"},
        {"device_id": "short_hopper_4", "device_type": "short_hopper"},
        # 无料仓 (2个)
        {"device_id": "no_hopper_1", "device_type": "no_hopper"},
        {"device_id": "no_hopper_2", "device_type": "no_hopper"},
        # 长料仓 (3个)
        {"device_id": "long_hopper_1", "device_type": "long_hopper"},
        {"device_id": "long_hopper_2", "device_type": "long_hopper"},
        {"device_id": "long_hopper_3", "device_type": "long_hopper"},
    ]
    
    for hopper in hoppers:
        # 电表数据
        write_point(
            measurement="sensor_data",
            tags={
                "device_id": hopper["device_id"],
                "device_type": hopper["device_type"],
                "module_type": "ElectricityMeter",
                "module_tag": "elec",
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
                "device_id": hopper["device_id"],
                "device_type": hopper["device_type"],
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
                "device_id": hopper["device_id"],
                "device_type": hopper["device_type"],
                "module_type": "WeighSensor",
                "module_tag": "weight",
                "db_number": "8"
            },
            fields={
                "weight": round(random.uniform(500, 2000), 2),
                "feed_rate": round(random.uniform(10, 50), 2),
            }
        )
    
    print(f"  [OK] 插入 {len(hoppers)} 个料仓的模拟数据")


def seed_roller_kiln_data():
    """插入辊道窑模拟数据"""
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
                "Pt": round(random.uniform(100, 300), 2),
                "ImpEp": round(random.uniform(5000, 15000), 2),
                "Ua_0": round(random.uniform(220, 240), 2),
                "Ua_1": round(random.uniform(220, 240), 2),
                "Ua_2": round(random.uniform(220, 240), 2),
                "I_0": round(random.uniform(20, 50), 2),
                "I_1": round(random.uniform(20, 50), 2),
                "I_2": round(random.uniform(20, 50), 2),
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
                "temperature": round(random.uniform(800, 1200), 2),
            }
        )
    
    print(f"  [OK] 插入辊道窑 {len(zones)} 个温区的模拟数据")


def seed_scr_data():
    """插入SCR设备模拟数据"""
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
                "Pt": round(random.uniform(80, 200), 2),
                "ImpEp": round(random.uniform(2000, 8000), 2),
                "Ua_0": round(random.uniform(220, 240), 2),
                "Ua_1": round(random.uniform(220, 240), 2),
                "Ua_2": round(random.uniform(220, 240), 2),
                "I_0": round(random.uniform(15, 35), 2),
                "I_1": round(random.uniform(15, 35), 2),
                "I_2": round(random.uniform(15, 35), 2),
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
                "flow_rate": round(random.uniform(50, 150), 2),
                "total_flow": round(random.uniform(10000, 50000), 2),
            }
        )
    
    print(f"  [OK] 插入 {len(scr_devices)} 台SCR设备的模拟数据")


def seed_fan_data():
    """插入风机模拟数据"""
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
                "Pt": round(random.uniform(30, 100), 2),
                "ImpEp": round(random.uniform(500, 3000), 2),
                "Ua_0": round(random.uniform(220, 240), 2),
                "Ua_1": round(random.uniform(220, 240), 2),
                "Ua_2": round(random.uniform(220, 240), 2),
                "I_0": round(random.uniform(5, 20), 2),
                "I_1": round(random.uniform(5, 20), 2),
                "I_2": round(random.uniform(5, 20), 2),
            }
        )
    
    print(f"  [OK] 插入 {len(fan_devices)} 台风机的模拟数据")
