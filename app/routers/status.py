# ============================================================
# 文件说明: status.py - 传感器状态位API路由
# ============================================================
# 功能:
#   - 获取所有传感器的通信状态
#   - 按设备类型过滤状态数据
#   - 为前端提供实时状态监控
# ============================================================

from fastapi import APIRouter, Query
from typing import Optional, List, Dict, Any

from app.services.polling_service import (
    get_all_status,
    get_status_by_device,
    get_status_by_type
)

router = APIRouter(prefix="/api/status", tags=["设备状态位"])


@router.get("/all")
async def get_all_sensor_status():
    """获取所有传感器的状态位数据
    
    Returns:
        {
            "success": true,
            "data": {
                "device_id": {
                    "device_id": "short_hopper_1_weight",
                    "device_type": "weight_sensor",
                    "description": "1号短料仓称重",
                    "done": true,
                    "busy": false,
                    "error": false,
                    "status_code": 0,
                    "timestamp": "2025-12-26T16:25:02Z"
                },
                ...
            },
            "error": null
        }
    """
    try:
        status_data = get_all_status()
        return {
            "success": True,
            "data": status_data,
            "error": None
        }
    except Exception as e:
        return {
            "success": False,
            "data": None,
            "error": str(e)
        }


@router.get("/device/{device_id}")
async def get_device_status(device_id: str):
    """获取单个设备的状态位数据
    
    Args:
        device_id: 设备ID (如: short_hopper_1_weight)
    
    Returns:
        {
            "success": true,
            "data": {
                "device_id": "short_hopper_1_weight",
                "device_type": "weight_sensor",
                "done": true,
                "busy": false,
                "error": false,
                "status_code": 0
            },
            "error": null
        }
    """
    try:
        status = get_status_by_device(device_id)
        
        if status is None:
            return {
                "success": False,
                "data": None,
                "error": f"设备 {device_id} 不存在"
            }
        
        return {
            "success": True,
            "data": status,
            "error": None
        }
    except Exception as e:
        return {
            "success": False,
            "data": None,
            "error": str(e)
        }


@router.get("/by-type")
async def get_status_by_device_type(
    device_type: str = Query(..., description="设备类型: electricity_meter, temperature_sensor, weight_sensor, flow_meter")
):
    """按设备类型获取状态位数据
    
    Args:
        device_type: 设备类型
            - electricity_meter: 电表
            - temperature_sensor: 温度传感器
            - weight_sensor: 称重传感器
            - flow_meter: 流量计
    
    Returns:
        {
            "success": true,
            "data": [
                {
                    "device_id": "short_hopper_1_weight",
                    "device_type": "weight_sensor",
                    "done": true,
                    "busy": false,
                    "error": false,
                    "status_code": 0
                },
                ...
            ],
            "error": null
        }
    """
    try:
        status_list = get_status_by_type(device_type)
        
        return {
            "success": True,
            "data": status_list,
            "error": None
        }
    except Exception as e:
        return {
            "success": False,
            "data": None,
            "error": str(e)
        }


@router.get("/errors")
async def get_error_devices():
    """获取所有通信错误的设备
    
    Returns:
        {
            "success": true,
            "data": {
                "total_errors": 2,
                "error_devices": [
                    {
                        "device_id": "short_hopper_1_weight",
                        "device_type": "weight_sensor",
                        "description": "1号短料仓称重",
                        "error": true,
                        "status_code": 8195
                    },
                    ...
                ]
            },
            "error": null
        }
    """
    try:
        all_status = get_all_status()
        
        # 筛选出错误设备
        error_devices = [
            status for status in all_status.values()
            if status.get('error', False)
        ]
        
        return {
            "success": True,
            "data": {
                "total_errors": len(error_devices),
                "error_devices": error_devices
            },
            "error": None
        }
    except Exception as e:
        return {
            "success": False,
            "data": None,
            "error": str(e)
        }


@router.get("/summary")
async def get_status_summary():
    """获取状态位统计摘要
    
    Returns:
        {
            "success": true,
            "data": {
                "total_devices": 41,
                "normal_count": 39,
                "error_count": 2,
                "by_type": {
                    "electricity_meter": {"total": 19, "errors": 0},
                    "temperature_sensor": {"total": 15, "errors": 0},
                    "weight_sensor": {"total": 7, "errors": 2},
                    "flow_meter": {"total": 2, "errors": 0}
                }
            },
            "error": null
        }
    """
    try:
        all_status = get_all_status()
        
        # 统计各类型设备
        type_stats: Dict[str, Dict[str, int]] = {}
        
        for status in all_status.values():
            device_type = status.get('device_type', 'unknown')
            
            if device_type not in type_stats:
                type_stats[device_type] = {"total": 0, "errors": 0}
            
            type_stats[device_type]["total"] += 1
            
            if status.get('error', False):
                type_stats[device_type]["errors"] += 1
        
        # 计算总数
        total_devices = len(all_status)
        error_count = sum(1 for s in all_status.values() if s.get('error', False))
        normal_count = total_devices - error_count
        
        return {
            "success": True,
            "data": {
                "total_devices": total_devices,
                "normal_count": normal_count,
                "error_count": error_count,
                "by_type": type_stats
            },
            "error": None
        }
    except Exception as e:
        return {
            "success": False,
            "data": None,
            "error": str(e)
        }
