# 料仓设备API路由

from fastapi import APIRouter, Query, Path
from typing import Optional
from datetime import datetime, timedelta

from app.models.response import ApiResponse
from app.services.history_query_service import get_history_service
from app.services.polling_service import (
    get_latest_data,
    get_latest_device_data,
    get_latest_devices_by_type,
    get_latest_timestamp,
    is_polling_running
)

router = APIRouter(prefix="/api/hopper", tags=["料仓设备"])
# 🔧 删除模块级实例化，改为在函数内调用 get_history_service()

HOPPER_TYPES = ["short_hopper", "no_hopper", "long_hopper"]

# 静态设备列表（避免查询 InfluxDB）
HOPPER_DEVICES = {
    "short_hopper": [
        {"device_id": "short_hopper_1", "device_type": "short_hopper", "db_number": "8"},
        {"device_id": "short_hopper_2", "device_type": "short_hopper", "db_number": "8"},
        {"device_id": "short_hopper_3", "device_type": "short_hopper", "db_number": "8"},
        {"device_id": "short_hopper_4", "device_type": "short_hopper", "db_number": "8"},
    ],
    "no_hopper": [
        {"device_id": "no_hopper_1", "device_type": "no_hopper", "db_number": "8"},
        {"device_id": "no_hopper_2", "device_type": "no_hopper", "db_number": "8"},
    ],
    "long_hopper": [
        {"device_id": "long_hopper_1", "device_type": "long_hopper", "db_number": "8"},
        {"device_id": "long_hopper_2", "device_type": "long_hopper", "db_number": "8"},
        {"device_id": "long_hopper_3", "device_type": "long_hopper", "db_number": "8"},
    ],
}


# ============================================================
# 1. GET /api/hopper/realtime/batch - 批量获取所有料仓实时数据（内存缓存）
# ============================================================
@router.get("/realtime/batch")
async def get_all_hoppers_realtime(
    hopper_type: Optional[str] = Query(
        None,
        description="料仓类型筛选",
        enum=["short_hopper", "no_hopper", "long_hopper"],
        example="short_hopper"
    )
):
    """批量获取所有料仓的实时数据（从内存缓存读取，无需查询数据库）
    
    **优势**:
    - 🚀 从内存缓存读取，响应速度极快（<1ms）
    - 📊 适合大屏实时监控
    - ⚡ 无数据库压力
    
    **数据来源**: 内存缓存（由轮询服务实时更新）
    
    **返回结构**:
    ```json
    {
        "success": true,
        "data": {
            "total": 9,
            "source": "cache",
            "timestamp": "2025-12-25T10:00:00Z",
            "polling_running": true,
            "devices": [
                {
                    "device_id": "short_hopper_1",
                    "device_type": "short_hopper",
                    "timestamp": "2025-12-11T10:00:00Z",
                    "modules": {
                        "weight": {"module_type": "WeighSensor", "fields": {"weight": 1234.5, "feed_rate": 12.3}},
                        "temp": {"module_type": "TemperatureSensor", "fields": {"temperature": 85.5}},
                        "elec": {"module_type": "ElectricityMeter", "fields": {"Pt": 120.5, "Ua_0": 230.2}}
                    }
                },
                ...
            ]
        }
    }
    ```
    """
    try:
        # 从内存缓存获取数据
        if hopper_type:
            devices_data = get_latest_devices_by_type(hopper_type)
        else:
            all_data = get_latest_data()
            devices_data = [
                data for data in all_data.values()
                if data.get('device_type') in HOPPER_TYPES
            ]
        
        # 数据有效性检查
        if not devices_data:
            return ApiResponse.ok({
                "total": 0,
                "source": "cache",
                "timestamp": get_latest_timestamp(),
                "polling_running": is_polling_running(),
                "warning": "缓存为空，轮询服务可能未启动或首次轮询未完成",
                "devices": []
            })
        
        return ApiResponse.ok({
            "total": len(devices_data),
            "source": "cache",
            "timestamp": get_latest_timestamp(),
            "polling_running": is_polling_running(),
            "devices": devices_data
        })
    except Exception as e:
        return ApiResponse.fail(f"批量查询失败: {str(e)}")


# ============================================================
# 2. GET /api/hopper/{device_id} - 获取料仓实时数据（内存缓存）
# ============================================================
@router.get("/{device_id}")
async def get_hopper_realtime(
    device_id: str = Path(
        ..., 
        description="料仓设备ID",
        example="short_hopper_1"
    )
):
    """获取指定料仓的实时数据（从内存缓存读取）
    
    **数据来源**: 内存缓存（由轮询服务实时更新）
    
    **返回字段**:
    - `weight`: 实时重量 (kg)
    - `feed_rate`: 下料速度 (kg/h)
    - `temperature`: 温度 (°C)
    - `Pt`: 功率 (kW)
    - `ImpEp`: 电能 (kWh)
    - `Ua_0~2`: 三相电压 (V)
    - `I_0~2`: 三相电流 (A)
    """
    try:
        # 优先从内存缓存读取
        cached_data = get_latest_device_data(device_id)
        
        if cached_data:
            return ApiResponse.ok({
                "source": "cache",
                **cached_data
            })
        
        # 缓存无数据，查询 InfluxDB
        data = get_history_service().query_device_realtime(device_id)
        if not data:
            return ApiResponse.fail(f"设备 {device_id} 不存在或无数据")
        return ApiResponse.ok({
            "source": "influxdb",
            **data
        })
    except Exception as e:
        return ApiResponse.fail(f"查询失败: {str(e)}")

# ============================================================
# 3. GET /api/hopper/{device_id}/history - 获取料仓历史数据（InfluxDB）
# ============================================================
@router.get("/{device_id}/history")
async def get_hopper_history(
    device_id: str = Path(..., description="料仓设备ID", example="short_hopper_1"),
    start: Optional[datetime] = Query(None, description="开始时间", example="2025-12-10T00:00:00"),
    end: Optional[datetime] = Query(None, description="结束时间", example="2025-12-10T23:59:59"),
    module_type: Optional[str] = Query(
        None, 
        description="模块类型筛选",
        enum=["WeighSensor", "TemperatureSensor", "ElectricityMeter"],
        example="WeighSensor"
    ),
    fields: Optional[str] = Query(None, description="字段筛选 (逗号分隔)", example="weight,feed_rate"),
    interval: Optional[str] = Query("5m", description="聚合间隔", example="5m")
):
    """获取料仓设备的历史数据
    
    **可用字段**:
    - WeighSensor: `weight`, `feed_rate`
    - TemperatureSensor: `temperature`
    - ElectricityMeter: `Pt`, `ImpEp`, `Ua_0`, `Ua_1`, `Ua_2`, `I_0`, `I_1`, `I_2`
    
    **时间范围**: 默认查询最近1小时
    
    **示例**:
    ```
    GET /api/hopper/short_hopper_1/history
    GET /api/hopper/short_hopper_1/history?module_type=WeighSensor&fields=weight,feed_rate
    GET /api/hopper/short_hopper_1/history?start=2025-12-10T00:00:00&end=2025-12-10T12:00:00
    ```
    """
    try:
        # 默认时间范围：最近1小时
        if not start:
            start = datetime.now() - timedelta(hours=1)
        if not end:
            end = datetime.now()
        
        # 解析字段列表
        field_list = fields.split(",") if fields else None
        
        data = get_history_service().query_device_history(
            device_id=device_id,
            start=start,
            end=end,
            module_type=module_type,
            fields=field_list,
            interval=interval
        )
        
        return ApiResponse.ok({
            "device_id": device_id,
            "time_range": {
                "start": start.isoformat(),
                "end": end.isoformat()
            },
            "interval": interval,
            "data": data
        })
    except Exception as e:
        return ApiResponse.fail(f"查询失败: {str(e)}")
