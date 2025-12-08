# ============================================================
# 文件说明: kiln.py - 窑炉数据路由 (辊道窑 + 回转窑)
# ============================================================
# 接口列表:
# 1. GET /roller/realtime       - 辊道窑实时数据
# 2. GET /roller/history        - 辊道窑历史数据
# 3. GET /rotary                - 回转窑列表
# 4. GET /rotary/{id}/realtime  - 回转窑实时数据
# 5. GET /rotary/{id}/history   - 回转窑历史数据
# ============================================================

from fastapi import APIRouter, Query, Path, HTTPException
from datetime import datetime, timedelta
from typing import Optional, List

from config import get_settings
from app.models.kiln import (
    RollerKilnRealtime, RotaryKilnRealtime,
    RollerKilnHistory, RotaryKilnHistory,
    DataInterval, QueryDimension
)
from app.models.response import ApiResponse
from app.core.influxdb import query_data

router = APIRouter()
settings = get_settings()


# ------------------------------------------------------------
# 1. GET /roller/realtime - 辊道窑实时数据
# ------------------------------------------------------------
@router.get("/roller/realtime", response_model=ApiResponse[RollerKilnRealtime])
async def get_roller_kiln_realtime():
    """获取辊道窑实时数据"""
    from app.services.plc_service import PLCService
    
    try:
        plc_service = PLCService()
        data = plc_service.read_roller_kiln_data()
        return ApiResponse.ok(data)
    except Exception as e:
        return ApiResponse.fail(f"读取辊道窑数据失败: {str(e)}")


# ------------------------------------------------------------
# 2. GET /roller/history - 辊道窑历史数据
# ------------------------------------------------------------
@router.get("/roller/history", response_model=ApiResponse[RollerKilnHistory])
async def get_roller_kiln_history(
    start: datetime = Query(..., description="开始时间"),
    end: datetime = Query(..., description="结束时间"),
    interval: DataInterval = Query(DataInterval.ONE_MIN, description="数据间隔"),
    zone_ids: Optional[str] = Query(None, description="温区ID，逗号分隔")
):
    """获取辊道窑历史数据"""
    # 解析温区ID
    zone_id_list = None
    if zone_ids:
        zone_id_list = [int(x.strip()) for x in zone_ids.split(",")]
    
    # 查询温度数据
    temp_data = query_data(
        measurement="roller_kiln_temp",
        start_time=start,
        end_time=end,
        interval=interval.value
    )
    
    # 查询能耗数据
    energy_data = query_data(
        measurement="roller_kiln_energy",
        start_time=start,
        end_time=end,
        interval=interval.value
    )
    
    # TODO: 组装完整的历史数据响应
    return ApiResponse.ok(RollerKilnHistory(
        start_time=start,
        end_time=end,
        interval=interval.value,
        data=[]  # 需要组装数据
    ))


# ------------------------------------------------------------
# 3. GET /rotary - 回转窑列表
# ------------------------------------------------------------
@router.get("/rotary")
async def get_rotary_kiln_list():
    """获取回转窑设备列表"""
    devices = [
        {"device_id": 1, "device_name": "回转窑1号", "status": True},
        {"device_id": 2, "device_name": "回转窑2号", "status": True},
        {"device_id": 3, "device_name": "回转窑3号", "status": True},
    ]
    return ApiResponse.ok(devices)


# ------------------------------------------------------------
# 4. GET /rotary/{id}/realtime - 回转窑实时数据
# ------------------------------------------------------------
@router.get("/rotary/{device_id}/realtime", response_model=ApiResponse[RotaryKilnRealtime])
async def get_rotary_kiln_realtime(
    device_id: int = Path(..., ge=1, le=7, description="设备ID 1-7")
):
    """获取回转窑实时数据"""
    from app.services.plc_service import PLCService
    
    try:
        plc_service = PLCService()
        data = plc_service.read_rotary_kiln_data(device_id)
        return ApiResponse.ok(data)
    except Exception as e:
        return ApiResponse.fail(f"读取回转窑{device_id}数据失败: {str(e)}")


# ------------------------------------------------------------
# 5. GET /rotary/{id}/history - 回转窑历史数据
# ------------------------------------------------------------
@router.get("/rotary/{device_id}/history", response_model=ApiResponse[RotaryKilnHistory])
async def get_rotary_kiln_history(
    device_id: int = Path(..., ge=1, le=3, description="设备ID 1-3"),
    start: datetime = Query(..., description="开始时间"),
    end: datetime = Query(..., description="结束时间"),
    interval: DataInterval = Query(DataInterval.ONE_MIN, description="数据间隔"),
    dimension: Optional[QueryDimension] = Query(None, description="查询维度"),
    data_type: Optional[str] = Query(None, description="数据类型: temperature/energy/feed/hopper")
):
    """获取回转窑历史数据"""
    # 查询温度数据
    temp_data = query_data(
        measurement="rotary_kiln_temp",
        start_time=start,
        end_time=end,
        tags={"device_id": str(device_id)},
        interval=interval.value
    )
    
    # TODO: 组装完整的历史数据响应
    return ApiResponse.ok(RotaryKilnHistory(
        device_id=device_id,
        start_time=start,
        end_time=end,
        interval=interval.value,
        dimension=dimension.value if dimension else None,
        data=[]  # 需要组装数据
    ))
