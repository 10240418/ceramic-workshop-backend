# ============================================================
# 文件说明: plc_config.py - PLC 配置管理 API
# ============================================================
# API 列表:
# GET  /api/plc-config                     - 获取配置摘要
# GET  /api/plc-config/{device_type}       - 获取设备数据点
# POST /api/plc-config/{device_type}/point - 添加数据点
# PUT  /api/plc-config/{device_type}/point/{point_id} - 更新数据点
# POST /api/plc-config/reload              - 热重载配置
# GET  /api/plc-config/schema              - 获取生成的 Schema
# ============================================================

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Any, Optional

from app.core.plc_config_manager import PLCConfigManager, PLCDataType

router = APIRouter(prefix="/api/plc-config", tags=["PLC配置"])

# 全局配置管理器实例
config_manager = PLCConfigManager()


# ============================================================
# Pydantic 模型定义
# ============================================================

class DataPointCreate(BaseModel):
    """创建数据点请求"""
    name: str
    point_id: str
    db_offset: int
    data_type: str
    scale: float = 1.0
    unit: str = ""
    measurement: str
    field_name: str
    tags: Dict[str, str] = {}
    enabled: bool = True
    bit_offset: Optional[int] = None


class DataPointUpdate(BaseModel):
    """更新数据点请求"""
    name: Optional[str] = None
    db_offset: Optional[int] = None
    data_type: Optional[str] = None
    scale: Optional[float] = None
    unit: Optional[str] = None
    measurement: Optional[str] = None
    field_name: Optional[str] = None
    tags: Optional[Dict[str, str]] = None
    enabled: Optional[bool] = None
    bit_offset: Optional[int] = None


class DataPointResponse(BaseModel):
    """数据点响应"""
    name: str
    point_id: str
    db_offset: int
    data_type: str
    scale: float
    unit: str
    measurement: str
    field_name: str
    tags: Dict[str, str]
    enabled: bool
    bit_offset: Optional[int] = None


# ============================================================
# API 端点
# ============================================================

# ------------------------------------------------------------
# 1. GET /api/plc-config - 获取配置摘要
# ------------------------------------------------------------
@router.get("")
async def get_config_summary():
    """获取配置摘要"""
    try:
        summary = config_manager.get_summary()
        return {
            "success": True,
            "data": summary
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------
# 2. GET /api/plc-config/{device_type} - 获取设备数据点
# ------------------------------------------------------------
@router.get("/{device_type}")
async def get_device_points(
    device_type: str,
    enabled_only: bool = False
):
    """获取指定设备的数据点列表
    
    Args:
        device_type: 设备类型 (roller_kiln, rotary_kiln, scr)
        enabled_only: 是否只返回启用的数据点
    """
    try:
        points = config_manager.get_device_points(device_type, enabled_only)
        
        if not points:
            raise HTTPException(
                status_code=404, 
                detail=f"设备类型不存在或无数据点: {device_type}"
            )
        
        # 转换为响应格式
        points_data = []
        for p in points:
            points_data.append({
                "name": p.name,
                "point_id": p.point_id,
                "db_offset": p.db_offset,
                "data_type": p.data_type.value,
                "scale": p.scale,
                "unit": p.unit,
                "measurement": p.measurement,
                "field_name": p.field_name,
                "tags": p.tags,
                "enabled": p.enabled,
                "bit_offset": p.bit_offset
            })
        
        return {
            "success": True,
            "data": {
                "device_type": device_type,
                "total": len(points_data),
                "points": points_data
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------
# 3. POST /api/plc-config/{device_type}/point - 添加数据点
# ------------------------------------------------------------
@router.post("/{device_type}/point")
async def add_data_point(device_type: str, point: DataPointCreate):
    """添加新数据点
    
    Args:
        device_type: 设备类型
        point: 数据点配置
    """
    try:
        # 验证数据类型
        if point.data_type not in [t.value for t in PLCDataType]:
            raise HTTPException(
                status_code=400,
                detail=f"无效的数据类型: {point.data_type}"
            )
        
        # 添加数据点
        success = config_manager.add_data_point(
            device_type,
            point.dict()
        )
        
        if not success:
            raise HTTPException(status_code=400, detail="添加数据点失败")
        
        return {
            "success": True,
            "message": f"数据点添加成功: {point.name}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------
# 4. PUT /api/plc-config/{device_type}/point/{point_id} - 更新数据点
# ------------------------------------------------------------
@router.put("/{device_type}/point/{point_id}")
async def update_data_point(
    device_type: str,
    point_id: str,
    updates: DataPointUpdate
):
    """更新数据点配置
    
    Args:
        device_type: 设备类型
        point_id: 数据点ID
        updates: 更新的字段
    """
    try:
        # 只保留非 None 的字段
        update_dict = {
            k: v for k, v in updates.dict().items() 
            if v is not None
        }
        
        if not update_dict:
            raise HTTPException(status_code=400, detail="没有提供更新字段")
        
        # 更新数据点
        success = config_manager.update_data_point(
            device_type,
            point_id,
            update_dict
        )
        
        if not success:
            raise HTTPException(status_code=400, detail="更新数据点失败")
        
        return {
            "success": True,
            "message": f"数据点更新成功: {point_id}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------
# 5. POST /api/plc-config/reload - 热重载配置
# ------------------------------------------------------------
@router.post("/reload")
async def reload_config():
    """热重载配置文件"""
    try:
        config_manager.reload_config()
        return {
            "success": True,
            "message": "配置重载成功"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------
# 6. GET /api/plc-config/schema - 获取生成的 Schema
# ------------------------------------------------------------
@router.get("/schema/generate")
async def get_generated_schema():
    """获取自动生成的 InfluxDB Schema"""
    try:
        schema = config_manager.generate_schema()
        measurements_list = config_manager.list_measurements()
        
        return {
            "success": True,
            "data": {
                "measurements": schema,
                "measurement_names": measurements_list,
                "total": len(measurements_list)
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------
# 7. POST /api/plc-config/validate - 验证配置
# ------------------------------------------------------------
@router.post("/validate")
async def validate_config():
    """验证配置有效性"""
    try:
        errors = config_manager.validate_config()
        
        if not errors:
            return {
                "success": True,
                "message": "配置验证通过",
                "errors": {}
            }
        else:
            return {
                "success": False,
                "message": "配置验证失败",
                "errors": errors
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
