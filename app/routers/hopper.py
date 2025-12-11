# ============================================================
# 文件说明: hopper.py - 料仓设备API路由
# ============================================================
# 接口列表:
# 1. GET /api/hopper/list              - 获取所有料仓列表
# 2. GET /api/hopper/realtime/batch    - 批量获取所有料仓实时数据
# 3. GET /api/hopper/{device_id}       - 获取料仓实时数据
# 4. GET /api/hopper/{device_id}/history - 获取料仓历史数据
# ============================================================

from fastapi import APIRouter, Query, Path
from typing import Optional
from datetime import datetime, timedelta

from app.models.response import ApiResponse
from app.services.history_query_service import HistoryQueryService

router = APIRouter(prefix="/api/hopper", tags=["料仓设备"])

# 初始化查询服务
query_service = HistoryQueryService()

# 料仓设备类型
HOPPER_TYPES = ["short_hopper", "no_hopper", "long_hopper"]


# ============================================================
# 1. GET /api/hopper/list - 获取所有料仓列表
# ============================================================
@router.get("/list")
async def get_hopper_list(
    hopper_type: Optional[str] = Query(
        None, 
        description="料仓类型筛选",
        enum=["short_hopper", "no_hopper", "long_hopper"],
        example="short_hopper"
    )
):
    """获取所有料仓设备列表
    
    **料仓类型**:
    - `short_hopper`: 短料仓 (4个)
    - `no_hopper`: 无料仓 (2个)
    - `long_hopper`: 长料仓 (3个)
    
    **示例**:
    ```
    GET /api/hopper/list
    GET /api/hopper/list?hopper_type=short_hopper
    ```
    """
    try:
        # 如果指定了类型，只查该类型
        if hopper_type:
            data = query_service.query_device_list(hopper_type)
        else:
            # 查询所有料仓类型
            data = []
            for htype in HOPPER_TYPES:
                devices = query_service.query_device_list(htype)
                if devices:
                    data.extend(devices)
        
        return ApiResponse.ok(data)
    except Exception as e:
        return ApiResponse.fail(f"查询失败: {str(e)}")


# ============================================================
# 2. GET /api/hopper/realtime/batch - 批量获取所有料仓实时数据
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
    """批量获取所有料仓的实时数据（一次请求获取所有数据）
    
    **优势**:
    - 🚀 一次请求获取所有料仓数据，无需9次请求
    - 📊 适合大屏实时监控
    - ⚡ 减少网络开销
    
    **返回结构**:
    ```json
    {
        "success": true,
        "data": {
            "total": 9,
            "devices": [
                {
                    "device_id": "short_hopper_1",
                    "device_type": "short_hopper",
                    "timestamp": "2025-12-11T10:00:00Z",
                    "modules": {
                        "weight": {"weight": 1234.5, "feed_rate": 12.3},
                        "temp": {"temperature": 85.5},
                        "elec": {"Pt": 120.5, "Ua_0": 230.2, ...}
                    }
                },
                ...
            ]
        }
    }
    ```
    
    **示例**:
    ```
    GET /api/hopper/realtime/batch              # 获取所有料仓
    GET /api/hopper/realtime/batch?hopper_type=short_hopper  # 只获取短料仓
    ```
    """
    try:
        # 获取设备列表
        if hopper_type:
            device_list = query_service.query_device_list(hopper_type)
        else:
            device_list = []
            for htype in HOPPER_TYPES:
                devices = query_service.query_device_list(htype)
                if devices:
                    device_list.extend(devices)
        
        # 批量查询实时数据
        devices_data = []
        for device_info in device_list:
            device_id = device_info["device_id"]
            try:
                realtime_data = query_service.query_device_realtime(device_id)
                if realtime_data:
                    devices_data.append({
                        "device_id": device_id,
                        "device_type": device_info["device_type"],
                        "db_number": device_info.get("db_number"),
                        **realtime_data
                    })
            except Exception as e:
                print(f"⚠️  查询 {device_id} 失败: {str(e)}")
                continue
        
        return ApiResponse.ok({
            "total": len(devices_data),
            "devices": devices_data
        })
    except Exception as e:
        return ApiResponse.fail(f"批量查询失败: {str(e)}")


# ============================================================
# 3. GET /api/hopper/{device_id} - 获取料仓实时数据
# ============================================================
@router.get("/{device_id}")
async def get_hopper_realtime(
    device_id: str = Path(
        ..., 
        description="料仓设备ID",
        example="short_hopper_1"
    )
):
    """获取指定料仓的实时数据
    
    **返回字段**:
    - `weight`: 实时重量 (kg)
    - `feed_rate`: 下料速度 (kg/s)
    - `temperature`: 温度 (°C)
    - `Pt`: 功率 (kW)
    - `ImpEp`: 电能 (kWh)
    - `Ua_0~2`: 三相电压 (V)
    - `I_0~2`: 三相电流 (A)
    
    **示例**:
    ```
    GET /api/hopper/short_hopper_1
    GET /api/hopper/long_hopper_2
    ```
    """
    try:
        data = query_service.query_device_realtime(device_id)
        if not data:
            return ApiResponse.fail(f"设备 {device_id} 不存在或无数据")
        return ApiResponse.ok(data)
    except Exception as e:
        return ApiResponse.fail(f"查询失败: {str(e)}")

# ============================================================
# 4. GET /api/hopper/{device_id}/history - 获取料仓历史数据
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
        
        data = query_service.query_device_history(
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
