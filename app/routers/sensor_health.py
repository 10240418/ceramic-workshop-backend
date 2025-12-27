# -*- coding: utf-8 -*-
"""
传感器健康检测 API
检查每个传感器在最近N分钟内是否有数据写入InfluxDB
"""

from fastapi import APIRouter, Query
from typing import Dict, Any, List
from datetime import datetime, timedelta

from app.core.influxdb import get_influx_client
from config import get_settings

router = APIRouter(prefix="/api/health", tags=["传感器健康检测"])

settings = get_settings()


# ============================================================
# 设备配置（与 config_*.yaml 保持一致）
# ============================================================

# 回转窑设备列表（9个）
HOPPER_DEVICES = [
    {"device_id": "short_hopper_1", "name": "短料仓1", "modules": ["ElectricityMeter", "TemperatureSensor", "WeighSensor"]},
    {"device_id": "short_hopper_2", "name": "短料仓2", "modules": ["ElectricityMeter", "TemperatureSensor", "WeighSensor"]},
    {"device_id": "short_hopper_3", "name": "短料仓3", "modules": ["ElectricityMeter", "TemperatureSensor", "WeighSensor"]},
    {"device_id": "short_hopper_4", "name": "短料仓4", "modules": ["ElectricityMeter", "TemperatureSensor", "WeighSensor"]},
    {"device_id": "no_hopper_1", "name": "无料仓1", "modules": ["ElectricityMeter", "TemperatureSensor"]},
    {"device_id": "no_hopper_2", "name": "无料仓2", "modules": ["ElectricityMeter", "TemperatureSensor"]},
    {"device_id": "long_hopper_1", "name": "长料仓1", "modules": ["ElectricityMeter", "TemperatureSensor", "WeighSensor"]},
    {"device_id": "long_hopper_2", "name": "长料仓2", "modules": ["ElectricityMeter", "TemperatureSensor", "WeighSensor"]},
    {"device_id": "long_hopper_3", "name": "长料仓3", "modules": ["ElectricityMeter", "TemperatureSensor", "WeighSensor"]},
]

# 辊道窑（1个设备，但有6个温区）
# 实际存储：device_id="roller_kiln_1"，通过 module_tag 区分温区
# module_tag: zone1_temp, zone2_temp, ..., zone6_temp (温度)
# module_tag: main_meter, zone1_meter, ..., zone5_meter (电表)
ROLLER_KILN_ZONES = [
    {"zone_tag": "zone1", "name": "辊道窑1号区", "temp_tag": "zone1_temp", "meter_tag": "zone1_meter"},
    {"zone_tag": "zone2", "name": "辊道窑2号区", "temp_tag": "zone2_temp", "meter_tag": "zone2_meter"},
    {"zone_tag": "zone3", "name": "辊道窑3号区", "temp_tag": "zone3_temp", "meter_tag": "zone3_meter"},
    {"zone_tag": "zone4", "name": "辊道窑4号区", "temp_tag": "zone4_temp", "meter_tag": "zone4_meter"},
    {"zone_tag": "zone5", "name": "辊道窑5号区", "temp_tag": "zone5_temp", "meter_tag": "zone5_meter"},
    {"zone_tag": "zone6", "name": "辊道窑6号区", "temp_tag": "zone6_temp", "meter_tag": None},  # 6号区只有温度，无电表
]

# 辊道窑主电表（单独检测）
ROLLER_KILN_MAIN = {"device_id": "roller_kiln_1", "name": "辊道窑主电表", "meter_tag": "main_meter"}

# SCR设备（2个）
SCR_DEVICES = [
    {"device_id": "scr_1", "name": "SCR设备1", "modules": ["ElectricityMeter", "FlowMeter"]},
    {"device_id": "scr_2", "name": "SCR设备2", "modules": ["ElectricityMeter", "FlowMeter"]},
]

# 风机设备（2个）
FAN_DEVICES = [
    {"device_id": "fan_1", "name": "风机1", "modules": ["ElectricityMeter"]},
    {"device_id": "fan_2", "name": "风机2", "modules": ["ElectricityMeter"]},
]

# 模块类型中文名称
MODULE_NAMES = {
    "ElectricityMeter": "电表",
    "TemperatureSensor": "温度",
    "WeighSensor": "称重",
    "FlowMeter": "燃气",
}


def _query_sensor_last_time(minutes: int = 30) -> Dict[str, Dict[str, Dict[str, datetime]]]:
    """
    查询每个传感器最后一次数据的时间
    
    健康检测只需要知道最后数据的时间，不需要具体值
    只查询数值类型字段（Pt, temperature, weight, flow_rate），避免 bool/float 类型冲突
    
    Returns:
        {
            "short_hopper_1": {
                "ElectricityMeter": {
                    "main": datetime(...),  # 默认模块
                },
                "TemperatureSensor": {
                    "main": datetime(...),
                },
                ...
            },
            "roller_kiln_1": {
                "TemperatureSensor": {
                    "zone1_temp": datetime(...),
                    "zone2_temp": datetime(...),
                    ...
                },
                "ElectricityMeter": {
                    "main_meter": datetime(...),
                    "zone1_meter": datetime(...),
                    ...
                }
            },
            ...
        }
    """
    client = get_influx_client()
    query_api = client.query_api()
    
    # 查询时增加 module_tag 分组，以区分辊道窑的不同温区
    flux_query = f'''
    from(bucket: "{settings.influx_bucket}")
        |> range(start: -{minutes}m)
        |> filter(fn: (r) => r["_measurement"] == "sensor_data")
        |> filter(fn: (r) => r["_field"] == "Pt" or r["_field"] == "temperature" or r["_field"] == "weight" or r["_field"] == "flow_rate")
        |> group(columns: ["device_id", "module_type", "module_tag"])
        |> last()
        |> keep(columns: ["device_id", "module_type", "module_tag", "_time"])
    '''
    
    print(f"📊 健康检查查询: bucket={settings.influx_bucket}, minutes={minutes}")
    print(f"📊 查询语句:\n{flux_query}")
    
    result: Dict[str, Dict[str, Dict[str, datetime]]] = {}
    
    try:
        tables = query_api.query(flux_query, org=settings.influx_org)
        
        record_count = 0
        for table in tables:
            for record in table.records:
                record_count += 1
                device_id = record.values.get("device_id", "")
                module_type = record.values.get("module_type", "")
                module_tag = record.values.get("module_tag", "main")  # 默认tag为main
                last_time = record.get_time()
                
                print(f"  📍 记录 {record_count}: device={device_id}, module={module_type}, tag={module_tag}, time={last_time}")
                
                if device_id and module_type:
                    if device_id not in result:
                        result[device_id] = {}
                    if module_type not in result[device_id]:
                        result[device_id][module_type] = {}
                    
                    # 记录每个 module_tag 的最新时间
                    existing_time = result[device_id][module_type].get(module_tag)
                    if existing_time is None or (last_time and last_time > existing_time):
                        result[device_id][module_type][module_tag] = last_time
        
        print(f"📊 健康检查结果: 查询到 {record_count} 条记录, {len(result)} 个设备")
        if result:
            print(f"📊 设备列表: {list(result.keys())}")
            for dev_id, modules in result.items():
                for mod_type, tags in modules.items():
                    print(f"   {dev_id}.{mod_type}: {list(tags.keys())}")
                    
    except Exception as e:
        print(f"❌ 查询传感器健康状态失败: {e}")
        import traceback
        traceback.print_exc()
    
    return result


def _check_device_health(
    device_config: Dict[str, Any],
    sensor_data: Dict[str, Dict[str, Dict[str, datetime]]],
) -> Dict[str, Any]:
    """检查单个设备的健康状态（回转窑、SCR、风机）"""
    device_id = device_config["device_id"]
    name = device_config["name"]
    modules = device_config["modules"]
    
    device_data = sensor_data.get(device_id, {})
    
    module_status = {}
    all_healthy = True
    last_seen = None
    
    for module in modules:
        # 获取该模块的所有 tag 数据，取最新时间
        module_tags = device_data.get(module, {})
        module_time = None
        for tag, time in module_tags.items():
            if module_time is None or (time and time > module_time):
                module_time = time
        
        is_healthy = module_time is not None
        
        module_status[module] = {
            "healthy": is_healthy,
            "name": MODULE_NAMES.get(module, module),
            "last_time": module_time.isoformat() if module_time else None,
        }
        
        if not is_healthy:
            all_healthy = False
        
        # 记录最后数据时间
        if module_time:
            if last_seen is None or module_time > last_seen:
                last_seen = module_time
    
    return {
        "device_id": device_id,
        "name": name,
        "healthy": all_healthy,
        "last_seen": last_seen.isoformat() if last_seen else None,
        "modules": module_status,
    }


def _check_roller_kiln_zone_health(
    zone_config: Dict[str, Any],
    sensor_data: Dict[str, Dict[str, Dict[str, datetime]]],
) -> Dict[str, Any]:
    """检查辊道窑单个温区的健康状态"""
    device_id = "roller_kiln_1"
    zone_tag = zone_config["zone_tag"]
    name = zone_config["name"]
    temp_tag = zone_config["temp_tag"]
    meter_tag = zone_config.get("meter_tag")
    
    device_data = sensor_data.get(device_id, {})
    
    module_status = {}
    all_healthy = True
    last_seen = None
    
    # 检查温度传感器
    temp_modules = device_data.get("TemperatureSensor", {})
    temp_time = temp_modules.get(temp_tag)
    temp_healthy = temp_time is not None
    
    module_status["TemperatureSensor"] = {
        "healthy": temp_healthy,
        "name": "温度",
        "tag": temp_tag,
        "last_time": temp_time.isoformat() if temp_time else None,
    }
    
    if not temp_healthy:
        all_healthy = False
    if temp_time and (last_seen is None or temp_time > last_seen):
        last_seen = temp_time
    
    # 检查电表（如果有）
    if meter_tag:
        meter_modules = device_data.get("ElectricityMeter", {})
        meter_time = meter_modules.get(meter_tag)
        meter_healthy = meter_time is not None
        
        module_status["ElectricityMeter"] = {
            "healthy": meter_healthy,
            "name": "电表",
            "tag": meter_tag,
            "last_time": meter_time.isoformat() if meter_time else None,
        }
        
        if not meter_healthy:
            all_healthy = False
        if meter_time and (last_seen is None or meter_time > last_seen):
            last_seen = meter_time
    
    return {
        "device_id": f"roller_kiln_{zone_tag}",  # 用于前端区分
        "name": name,
        "healthy": all_healthy,
        "last_seen": last_seen.isoformat() if last_seen else None,
        "modules": module_status,
    }


def _check_roller_kiln_main_health(
    sensor_data: Dict[str, Dict[str, Dict[str, datetime]]],
) -> Dict[str, Any]:
    """检查辊道窑主电表的健康状态"""
    device_id = "roller_kiln_1"
    device_data = sensor_data.get(device_id, {})
    
    # 检查主电表
    meter_modules = device_data.get("ElectricityMeter", {})
    meter_time = meter_modules.get("main_meter")
    meter_healthy = meter_time is not None
    
    return {
        "device_id": "roller_kiln_main",
        "name": "辊道窑主电表",
        "healthy": meter_healthy,
        "last_seen": meter_time.isoformat() if meter_time else None,
        "modules": {
            "ElectricityMeter": {
                "healthy": meter_healthy,
                "name": "主电表",
                "tag": "main_meter",
                "last_time": meter_time.isoformat() if meter_time else None,
            }
        },
    }


@router.get("/sensors")
async def get_sensor_health(
    minutes: int = Query(default=30, ge=1, le=1440, description="检查时间范围（分钟）")
) -> Dict[str, Any]:
    """
    获取所有传感器的健康状态
    
    检查每个传感器在最近N分钟内是否有数据：
    - 有数据 → healthy: true
    - 无数据 → healthy: false
    
    Args:
        minutes: 检查时间范围，默认30分钟
    
    Returns:
        {
            "success": true,
            "data": {
                "check_range_minutes": 30,
                "check_time": "2025-12-27T10:30:00",
                "summary": {
                    "total": 19,
                    "healthy": 15,
                    "unhealthy": 4
                },
                "devices": [
                    {
                        "device_id": "short_hopper_1",
                        "name": "短料仓1",
                        "healthy": true,
                        "last_seen": "2025-12-27T10:29:00",
                        "modules": {
                            "ElectricityMeter": {"healthy": true, "name": "电表", "last_time": "..."},
                            "TemperatureSensor": {"healthy": true, "name": "温度", "last_time": "..."},
                            "WeighSensor": {"healthy": false, "name": "称重", "last_time": null}
                        }
                    },
                    ...
                ]
            }
        }
    """
    from app.core.timezone_utils import now_beijing
    
    # 查询传感器最后数据时间
    sensor_data = _query_sensor_last_time(minutes)
    
    devices = []
    
    # 检查回转窑设备（9个）
    for config in HOPPER_DEVICES:
        health = _check_device_health(config, sensor_data)
        devices.append(health)
    
    # 检查辊道窑温区（6个）
    for zone_config in ROLLER_KILN_ZONES:
        health = _check_roller_kiln_zone_health(zone_config, sensor_data)
        devices.append(health)
    
    # 检查辊道窑主电表（1个）
    main_health = _check_roller_kiln_main_health(sensor_data)
    devices.append(main_health)
    
    # 检查SCR设备（2个）
    for config in SCR_DEVICES:
        health = _check_device_health(config, sensor_data)
        devices.append(health)
    
    # 检查风机设备（2个）
    for config in FAN_DEVICES:
        health = _check_device_health(config, sensor_data)
        devices.append(health)
    
    # 统计
    total = len(devices)
    healthy_count = sum(1 for d in devices if d["healthy"])
    unhealthy_count = total - healthy_count
    
    return {
        "success": True,
        "data": {
            "check_range_minutes": minutes,
            "check_time": now_beijing().isoformat(),
            "summary": {
                "total": total,
                "healthy": healthy_count,
                "unhealthy": unhealthy_count,
            },
            "devices": devices,
        },
        "error": None,
    }


@router.get("/sensors/summary")
async def get_sensor_health_summary(
    minutes: int = Query(default=30, ge=1, le=1440, description="检查时间范围（分钟）")
) -> Dict[str, Any]:
    """
    获取传感器健康状态摘要（简化版，仅返回异常设备）
    """
    result = await get_sensor_health(minutes)
    
    if not result["success"]:
        return result
    
    # 只返回异常设备
    unhealthy_devices = [
        d for d in result["data"]["devices"] if not d["healthy"]
    ]
    
    return {
        "success": True,
        "data": {
            "check_range_minutes": minutes,
            "check_time": result["data"]["check_time"],
            "summary": result["data"]["summary"],
            "unhealthy_devices": unhealthy_devices,
        },
        "error": None,
    }
