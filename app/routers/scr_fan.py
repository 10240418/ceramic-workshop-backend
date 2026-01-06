# ============================================================
# 文件说明: scr_fan.py - SCR设备和风机API路由
# ============================================================
# 接口列表:
# 1. GET /api/scr-fan/realtime/batch       - 批量获取所有SCR+风机实时数据（内存缓存）
# 2. GET /api/scr/realtime/batch           - 批量获取所有SCR实时数据（内存缓存）
# 3. GET /api/scr/{device_id}              - 获取SCR实时数据（内存缓存）
# 4. GET /api/scr/{device_id}/history      - 获取SCR历史数据
# 5. GET /api/fan/realtime/batch           - 批量获取所有风机实时数据（内存缓存）
# 6. GET /api/fan/{device_id}              - 获取风机实时数据（内存缓存）
# 7. GET /api/fan/{device_id}/history      - 获取风机历史数据
# ============================================================

from fastapi import APIRouter, Query, Path
from typing import Optional
from datetime import datetime, timedelta

from app.models.response import ApiResponse
from app.services.history_query_service import get_history_service
from app.services.polling_service import (
    get_latest_data,
    get_latest_device_data,
    get_latest_timestamp,
    is_polling_running
)

router = APIRouter(tags=["SCR设备和风机"])

# 🔧 删除模块级实例化，改为在函数内调用 get_history_service()

# 静态设备列表
SCR_DEVICES = ["scr_1", "scr_2"]
FAN_DEVICES = ["fan_1", "fan_2"]


# ============================================================
# 统一批量查询 API（内存缓存）
# ============================================================

# ============================================================
# GET /api/scr-fan/realtime/batch - 批量获取所有SCR+风机实时数据（内存缓存）
# ============================================================
@router.get("/api/scr-fan/realtime/batch")
async def get_all_scr_fan_realtime():
    """批量获取所有SCR设备和风机的实时数据（从内存缓存读取）
    
    **数据来源**: 内存缓存（由轮询服务实时更新）
    
    **返回结构**:
    ```json
    {
        "success": true,
        "data": {
            "total": 4,
            "source": "cache",
            "timestamp": "2025-12-25T10:00:00Z",
            "scr": {
                "total": 2,
                "devices": [...]
            },
            "fan": {
                "total": 2,
                "devices": [...]
            }
        }
    }
    ```
    """
    try:
        # 从内存缓存获取 SCR 设备数据
        scr_data = []
        for device_id in SCR_DEVICES:
            cached = get_latest_device_data(device_id)
            if cached:
                scr_data.append(cached)
        
        # 从内存缓存获取风机设备数据
        fan_data = []
        for device_id in FAN_DEVICES:
            cached = get_latest_device_data(device_id)
            if cached:
                fan_data.append(cached)
        
        return ApiResponse.ok({
            "total": len(scr_data) + len(fan_data),
            "source": "cache",
            "timestamp": get_latest_timestamp(),
            "polling_running": is_polling_running(),
            "scr": {
                "total": len(scr_data),
                "devices": scr_data
            },
            "fan": {
                "total": len(fan_data),
                "devices": fan_data
            }
        })
    except Exception as e:
        return ApiResponse.fail(f"批量查询失败: {str(e)}")


# ============================================================
# SCR 设备 API（内存缓存）
# ============================================================

# ============================================================
# 1. GET /api/scr/realtime/batch - 批量获取所有SCR实时数据（内存缓存）
# ============================================================
@router.get("/api/scr/realtime/batch")
async def get_all_scr_realtime():
    """批量获取所有SCR设备的实时数据（从内存缓存读取）
    
    **数据来源**: 内存缓存（由轮询服务实时更新）
    """
    try:
        # 从内存缓存获取数据
        devices_data = []
        for device_id in SCR_DEVICES:
            cached = get_latest_device_data(device_id)
            if cached:
                devices_data.append(cached)
        
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
# 2. GET /api/scr/{device_id} - 获取SCR实时数据（内存缓存）
# ============================================================
@router.get("/api/scr/{device_id}")
async def get_scr_realtime(
    device_id: str = Path(..., description="SCR设备ID", example="scr_1")
):
    """获取指定SCR设备的实时数据（从内存缓存读取）
    
    **返回字段**:
    - 燃气表: `flow_rate` (m³/h), `total_flow` (m³)
    - 电表: `Pt`, `ImpEp`, `Ua_0~2`, `I_0~2`
    """
    try:
        # 优先从内存缓存读取
        cached = get_latest_device_data(device_id)
        if cached:
            return ApiResponse.ok({
                "source": "cache",
                **cached
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
# 3. GET /api/scr/{device_id}/history - 获取SCR历史数据
# ============================================================
@router.get("/api/scr/{device_id}/history")
async def get_scr_history(
    device_id: str = Path(..., description="SCR设备ID", example="scr_1"),
    start: Optional[datetime] = Query(None, description="开始时间", example="2025-12-10T00:00:00"),
    end: Optional[datetime] = Query(None, description="结束时间", example="2025-12-10T23:59:59"),
    module_type: Optional[str] = Query(
        None, 
        description="模块类型筛选",
        enum=["FlowMeter", "ElectricityMeter"],
        example="FlowMeter"
    ),
    fields: Optional[str] = Query(None, description="字段筛选 (逗号分隔)", example="flow_rate,total_flow"),
    interval: Optional[str] = Query("5m", description="聚合间隔", example="5m")
):
    """获取SCR设备的历史数据
    
    **可用字段**:
    - FlowMeter: `flow_rate`, `total_flow`
    - ElectricityMeter: `Pt`, `ImpEp`, `Ua_0`, `Ua_1`, `Ua_2`, `I_0`, `I_1`, `I_2`
    
    **示例**:
    ```
    GET /api/scr/scr_1/history
    GET /api/scr/scr_1/history?module_type=FlowMeter&fields=flow_rate
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


# ============================================================
# 风机 API（内存缓存）
# ============================================================

# ============================================================
# 4. GET /api/fan/realtime/batch - 批量获取所有风机实时数据（内存缓存）
# ============================================================
@router.get("/api/fan/realtime/batch")
async def get_all_fans_realtime():
    """批量获取所有风机设备的实时数据（从内存缓存读取）
    
    **数据来源**: 内存缓存（由轮询服务实时更新）
    """
    try:
        # 从内存缓存获取数据
        devices_data = []
        for device_id in FAN_DEVICES:
            cached = get_latest_device_data(device_id)
            if cached:
                devices_data.append(cached)
        
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
# 5. GET /api/fan/{device_id} - 获取风机实时数据（内存缓存）
# ============================================================
@router.get("/api/fan/{device_id}")
async def get_fan_realtime(
    device_id: str = Path(..., description="风机设备ID", example="fan_1")
):
    """获取指定风机的实时数据（从内存缓存读取）
    
    **数据来源**: 优先从内存缓存读取，未命中时查询 InfluxDB
    
    **返回字段**:
    - 电表: `Pt`, `ImpEp`, `Ua_0~2`, `I_0~2`
    """
    try:
        # 优先从内存缓存获取
        cached = get_latest_device_data(device_id)
        if cached:
            return ApiResponse.ok({
                **cached,
                "source": "cache"
            })
        
        # 缓存未命中，查询 InfluxDB
        data = get_history_service().query_device_realtime(device_id)
        if not data:
            return ApiResponse.fail(f"设备 {device_id} 不存在或无数据")
        return ApiResponse.ok({
            **data,
            "source": "influxdb"
        })
    except Exception as e:
        return ApiResponse.fail(f"查询失败: {str(e)}")


# ============================================================
# 6. GET /api/fan/{device_id}/history - 获取风机历史数据
# ============================================================
@router.get("/api/fan/{device_id}/history")
async def get_fan_history(
    device_id: str = Path(..., description="风机设备ID", example="fan_1"),
    start: Optional[datetime] = Query(None, description="开始时间", example="2025-12-10T00:00:00"),
    end: Optional[datetime] = Query(None, description="结束时间", example="2025-12-10T23:59:59"),
    fields: Optional[str] = Query(None, description="字段筛选 (逗号分隔)", example="Pt,ImpEp"),
    interval: Optional[str] = Query("5m", description="聚合间隔", example="5m")
):
    """获取风机设备的历史数据
    
    **可用字段**:
    - ElectricityMeter: `Pt`, `ImpEp`, `Ua_0`, `Ua_1`, `Ua_2`, `I_0`, `I_1`, `I_2`
    
    **示例**:
    ```
    GET /api/fan/fan_1/history
    GET /api/fan/fan_1/history?fields=Pt,ImpEp&interval=10m
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
            module_type="ElectricityMeter",  # 风机只有电表
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
