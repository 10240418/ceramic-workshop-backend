# ============================================================
# 文件说明: devices.py - 通用设备查询API路由
# ============================================================
# 接口列表:
# 1. GET /db/{db_number}/realtime - 按DB块批量获取实时数据
# 2. GET /db/{db_number}/list     - 按DB块获取设备列表
# ============================================================

from fastapi import APIRouter, Path
from typing import Dict, Any
import logging

from app.models.response import ApiResponse
from app.services.history_query_service import get_history_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/devices", tags=["通用设备查询"])

# [FIX] 删除模块级实例化，改为在函数内调用 get_history_service()


# ============================================================
# 1. GET /db/{db_number}/realtime - 按DB块批量获取实时数据
# ============================================================
@router.get("/db/{db_number}/realtime")
async def get_db_devices_realtime(
    db_number: int = Path(..., description="DB块号", example=8)
):
    """按DB块批量获取所有设备实时数据（终极优化方案）
    
    **优势**:
    -  按物理DB块分组查询
    -  一次请求获取整个DB块的所有设备数据
    -  配合 /api/config/db-mappings 动态适配
    
    **工作流程**:
    ```
    1. 前端启动时调用 GET /api/config/db-mappings
       了解所有DB块及其设备数量
    
    2. 根据DB块号批量查询实时数据
       GET /api/devices/db/8/realtime  → 9个料仓数据
       GET /api/devices/db/9/realtime  → 辊道窑6温区数据
       GET /api/devices/db/10/realtime → 2SCR+2风机数据
    
    3. 配置文件修改后，前端重新调用步骤1即可动态适配
    ```
    
    **返回结构**:
    ```json
    {
        "success": true,
        "data": {
            "db_number": 8,
            "db_name": "DB8_Hoppers",
            "total_devices": 9,
            "devices": [
                {
                    "device_id": "short_hopper_1",
                    "device_type": "short_hopper",
                    "timestamp": "2025-12-11T10:00:00Z",
                    "modules": {...}
                },
                ...
            ]
        }
    }
    ```
    
    **示例**:
    ```
    GET /api/devices/db/8/realtime   # 获取DB8（料仓）所有设备
    GET /api/devices/db/9/realtime   # 获取DB9（辊道窑）所有设备
    GET /api/devices/db/10/realtime  # 获取DB10（SCR/风机）所有设备
    ```
    """
    try:
        import yaml
        
        # 1. 读取 DB 映射配置
        with open("configs/db_mappings.yaml", "r", encoding="utf-8") as f:
            mappings = yaml.safe_load(f)
        
        db_info = None
        for db in mappings.get("db_mappings", []):
            if db["db_number"] == db_number:
                db_info = db
                break
        
        if not db_info:
            return ApiResponse.fail(f"DB{db_number} 不存在")
        
        # 2. 从 InfluxDB 查询该 DB 块下所有设备
        # 使用 db_number 作为 tag 过滤
        device_list = []
        
        # 先尝试从数据库查询
        all_devices = get_history_service().query_device_list()
        for device in all_devices:
            # 根据 device_id 判断属于哪个 DB 块
            if db_number == 8:  # 料仓
                if any(prefix in device["device_id"] for prefix in ["short_hopper", "no_hopper", "long_hopper"]):
                    device_list.append(device)
            elif db_number == 9:  # 辊道窑
                if "roller_kiln" in device["device_id"]:
                    device_list.append(device)
            elif db_number == 10:  # SCR/风机
                if any(prefix in device["device_id"] for prefix in ["scr_", "fan_"]):
                    device_list.append(device)
        
        # 3. 批量查询实时数据
        devices_data = []
        for device_info in device_list:
            device_id = device_info["device_id"]
            try:
                realtime_data = get_history_service().query_device_realtime(device_id)
                if realtime_data:
                    devices_data.append({
                        "device_id": device_id,
                        "device_type": device_info.get("device_type", ""),
                        "db_number": str(db_number),
                        **realtime_data
                    })
            except Exception as e:
                logger.warning("[Devices] query %s failed: %s", device_id, e)
                continue
        
        return ApiResponse.ok({
            "db_number": db_number,
            "db_name": db_info["db_name"],
            "description": db_info.get("description", ""),
            "total_devices": len(devices_data),
            "devices": devices_data
        })
    except Exception as e:
        logger.error("[Devices] query DB devices realtime failed: %s", e, exc_info=True)
        return ApiResponse.fail(f"查询失败: {str(e)}")


# ============================================================
# 2. GET /db/{db_number}/list - 按DB块获取设备列表
# ============================================================
@router.get("/db/{db_number}/list")
async def get_db_devices_list(
    db_number: int = Path(..., description="DB块号", example=8)
):
    """按DB块获取设备列表（不含实时数据）
    
    **返回**: 该DB块下所有设备的基本信息
    
    **示例**:
    ```
    GET /api/devices/db/8/list   # 获取DB8设备列表
    GET /api/devices/db/9/list   # 获取DB9设备列表
    GET /api/devices/db/10/list  # 获取DB10设备列表
    ```
    """
    try:
        # 查询该 DB 块下所有设备
        all_devices = get_history_service().query_device_list()
        device_list = []
        
        for device in all_devices:
            # 根据 device_id 判断属于哪个 DB 块
            if db_number == 8:  # 料仓
                if any(prefix in device["device_id"] for prefix in ["short_hopper", "no_hopper", "long_hopper"]):
                    device_list.append(device)
            elif db_number == 9:  # 辊道窑
                if "roller_kiln" in device["device_id"]:
                    device_list.append(device)
            elif db_number == 10:  # SCR/风机
                if any(prefix in device["device_id"] for prefix in ["scr_", "fan_"]):
                    device_list.append(device)
        
        return ApiResponse.ok({
            "db_number": db_number,
            "total": len(device_list),
            "devices": device_list
        })
    except Exception as e:
        logger.error("[Devices] query DB devices list failed: %s", e, exc_info=True)
        return ApiResponse.fail(f"查询失败: {str(e)}")
