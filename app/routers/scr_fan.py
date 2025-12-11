# ============================================================
# 文件说明: scr_fan.py - SCR设备和风机API路由
# ============================================================
# 接口列表:
# 1. GET /api/scr/list                  - 获取SCR设备列表
# 2. GET /api/scr/{device_id}           - 获取SCR实时数据
# 3. GET /api/scr/{device_id}/history   - 获取SCR历史数据
# 4. GET /api/fan/list                  - 获取风机列表
# 5. GET /api/fan/{device_id}           - 获取风机实时数据
# 6. GET /api/fan/{device_id}/history   - 获取风机历史数据
# ============================================================

from fastapi import APIRouter, Query, Path
from typing import Optional
from datetime import datetime, timedelta

from app.models.response import ApiResponse
from app.services.history_query_service import HistoryQueryService

router = APIRouter(tags=["SCR设备和风机"])

# 初始化查询服务
query_service = HistoryQueryService()


# ============================================================
# SCR 设备 API
# ============================================================

# ============================================================
# 1. GET /api/scr/list - 获取SCR设备列表
# ============================================================
@router.get("/api/scr/list")
async def get_scr_list():
    """获取所有SCR设备列表
    
    **返回**: SCR设备列表 (2台)
    """
    try:
        data = query_service.query_device_list("scr")
        return ApiResponse.ok(data)
    except Exception as e:
        return ApiResponse.fail(f"查询失败: {str(e)}")


# ============================================================
# 2. GET /api/scr/{device_id} - 获取SCR实时数据
# ============================================================
@router.get("/api/scr/{device_id}")
async def get_scr_realtime(
    device_id: str = Path(..., description="SCR设备ID", example="scr_1")
):
    """获取指定SCR设备的实时数据
    
    **返回字段**:
    - 燃气表: `flow_rate` (m³/h), `total_flow` (m³)
    - 电表: `Pt`, `ImpEp`, `Ua_0~2`, `I_0~2`
    
    **示例**:
    ```
    GET /api/scr/scr_1
    GET /api/scr/scr_2
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


# ============================================================
# 风机 API
# ============================================================

# ============================================================
# 4. GET /api/fan/list - 获取风机列表
# ============================================================
@router.get("/api/fan/list")
async def get_fan_list():
    """获取所有风机设备列表
    
    **返回**: 风机设备列表 (2台)
    """
    try:
        data = query_service.query_device_list("fan")
        return ApiResponse.ok(data)
    except Exception as e:
        return ApiResponse.fail(f"查询失败: {str(e)}")


# ============================================================
# 5. GET /api/fan/{device_id} - 获取风机实时数据
# ============================================================
@router.get("/api/fan/{device_id}")
async def get_fan_realtime(
    device_id: str = Path(..., description="风机设备ID", example="fan_1")
):
    """获取指定风机的实时数据
    
    **返回字段**:
    - 电表: `Pt`, `ImpEp`, `Ua_0~2`, `I_0~2`
    
    **示例**:
    ```
    GET /api/fan/fan_1
    GET /api/fan/fan_2
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
        
        data = query_service.query_device_history(
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
