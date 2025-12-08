# ============================================================
# 文件说明: scr.py - SCR设备数据路由
# ============================================================
# 接口列表:
# 1. GET /                      - SCR设备列表
# 2. GET /{id}/realtime         - SCR实时数据
# 3. GET /{id}/fans             - 风机数据
# 4. GET /{id}/pumps            - 氨水泵数据
# 5. GET /{id}/gas              - 燃气管路数据
# 6. GET /{id}/history          - 历史数据
# 7. GET /compare               - 多设备对比
# ============================================================

from fastapi import APIRouter, Query, Path
from datetime import datetime
from typing import Optional, List

from config import get_settings
from app.models.scr import SCRRealtime, SCRHistory, StatisticsPeriod, EquipmentType
from app.models.response import ApiResponse
from app.core.influxdb import query_data

router = APIRouter()
settings = get_settings()


# ------------------------------------------------------------
# 1. GET / - SCR设备列表
# ------------------------------------------------------------
@router.get("/")
async def get_scr_list():
    """获取SCR设备列表"""
    devices = [
        {"device_id": 1, "device_name": "SCR设备1号", "status": True},
        {"device_id": 2, "device_name": "SCR设备2号", "status": True},
    ]
    return ApiResponse.ok(devices)


# ------------------------------------------------------------
# 2. GET /{id}/realtime - SCR实时数据
# ------------------------------------------------------------
@router.get("/{device_id}/realtime", response_model=ApiResponse[SCRRealtime])
async def get_scr_realtime(
    device_id: int = Path(..., ge=1, le=2, description="设备ID 1-2")
):
    """获取SCR设备实时数据"""
    from app.services.plc_service import PLCService
    
    try:
        plc_service = PLCService()
        data = plc_service.read_scr_data(device_id)
        return ApiResponse.ok(data)
    except Exception as e:
        return ApiResponse.fail(f"读取SCR设备{device_id}数据失败: {str(e)}")


# ------------------------------------------------------------
# 3. GET /{id}/fans - 风机数据
# ------------------------------------------------------------
@router.get("/{device_id}/fans")
async def get_scr_fans(
    device_id: int = Path(..., ge=1, le=2, description="设备ID 1-2")
):
    """获取SCR风机数据"""
    from app.services.plc_service import PLCService
    
    try:
        plc_service = PLCService()
        data = plc_service.read_scr_data(device_id)
        return ApiResponse.ok(data.get('fans', []))
    except Exception as e:
        return ApiResponse.fail(f"读取SCR风机数据失败: {str(e)}")


# ------------------------------------------------------------
# 4. GET /{id}/pumps - 氨水泵数据
# ------------------------------------------------------------
@router.get("/{device_id}/pumps")
async def get_scr_pumps(
    device_id: int = Path(..., ge=1, le=2, description="设备ID 1-2")
):
    """获取SCR氨水泵数据"""
    from app.services.plc_service import PLCService
    
    try:
        plc_service = PLCService()
        data = plc_service.read_scr_data(device_id)
        return ApiResponse.ok(data.get('ammonia_pumps', []))
    except Exception as e:
        return ApiResponse.fail(f"读取SCR氨水泵数据失败: {str(e)}")


# ------------------------------------------------------------
# 5. GET /{id}/gas - 燃气管路数据
# ------------------------------------------------------------
@router.get("/{device_id}/gas")
async def get_scr_gas(
    device_id: int = Path(..., ge=1, le=2, description="设备ID 1-2")
):
    """获取SCR燃气管路数据"""
    from app.services.plc_service import PLCService
    
    try:
        plc_service = PLCService()
        data = plc_service.read_scr_data(device_id)
        return ApiResponse.ok(data.get('gas_pipelines', []))
    except Exception as e:
        return ApiResponse.fail(f"读取SCR燃气数据失败: {str(e)}")


# ------------------------------------------------------------
# 6. GET /{id}/history - 历史数据
# ------------------------------------------------------------
@router.get("/{device_id}/history", response_model=ApiResponse[SCRHistory])
async def get_scr_history(
    device_id: int = Path(..., ge=1, le=2, description="设备ID 1-2"),
    start: datetime = Query(..., description="开始时间"),
    end: datetime = Query(..., description="结束时间"),
    dimension: str = Query("hour", description="查询维度: hour/day/week/month/year"),
    equipment_type: EquipmentType = Query(EquipmentType.ALL, description="设备类型")
):
    """获取SCR设备历史数据"""
    # TODO: 实现历史数据查询
    return ApiResponse.ok(SCRHistory(
        device_ids=[device_id],
        start_time=start,
        end_time=end,
        dimension=dimension,
        data=[]
    ))


# ------------------------------------------------------------
# 7. GET /compare - 多设备对比
# ------------------------------------------------------------
@router.get("/compare")
async def compare_scr_devices(
    device_ids: str = Query(..., description="设备ID，逗号分隔"),
    start: datetime = Query(..., description="开始时间"),
    end: datetime = Query(..., description="结束时间"),
    dimension: str = Query("hour", description="查询维度")
):
    """多设备数据对比"""
    ids = [int(x.strip()) for x in device_ids.split(",")]
    
    # TODO: 实现多设备对比查询
    return ApiResponse.ok({
        "device_ids": ids,
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
        "dimension": dimension,
        "comparison_data": []
    })
