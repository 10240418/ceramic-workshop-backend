# ============================================================
# 文件说明: config.py - 系统配置路由
# ============================================================
# 接口列表:
# 1. GET /server            - 获取服务器配置
# 2. GET /plc               - 获取PLC配置
# 3. PUT /plc               - 更新PLC配置
# 4. POST /plc/test         - 测试PLC连接
# 5. GET /database          - 获取数据库配置
# 6. GET /sensors           - 获取传感器配置
# ============================================================

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from config import get_settings
from app.models.response import ApiResponse

router = APIRouter()
settings = get_settings()


# 配置更新模型
class PLCConfigUpdate(BaseModel):
    ip_address: Optional[str] = None
    rack: Optional[int] = None
    slot: Optional[int] = None
    timeout_ms: Optional[int] = None
    poll_interval: Optional[int] = None


# ------------------------------------------------------------
# 1. GET /server - 获取服务器配置
# ------------------------------------------------------------
@router.get("/server")
async def get_server_config():
    """获取服务器配置"""
    return ApiResponse.ok({
        "host": settings.server_host,
        "port": settings.server_port,
        "debug": settings.debug
    })


# ------------------------------------------------------------
# 2. GET /plc - 获取PLC配置
# ------------------------------------------------------------
@router.get("/plc")
async def get_plc_config():
    """获取PLC配置"""
    return ApiResponse.ok({
        "ip_address": settings.plc_ip,
        "rack": settings.plc_rack,
        "slot": settings.plc_slot,
        "timeout_ms": settings.plc_timeout,
        "poll_interval": settings.plc_poll_interval
    })


# ------------------------------------------------------------
# 3. PUT /plc - 更新PLC配置
# ------------------------------------------------------------
@router.put("/plc")
async def update_plc_config(config: PLCConfigUpdate):
    """更新PLC配置"""
    # TODO: 实现配置更新逻辑（保存到数据库）
    return ApiResponse.ok({
        "message": "配置更新成功（需重启生效）",
        "updated_fields": config.model_dump(exclude_none=True)
    })


# ------------------------------------------------------------
# 4. POST /plc/test - 测试PLC连接
# ------------------------------------------------------------
@router.post("/plc/test")
async def test_plc_connection():
    """测试PLC连接"""
    try:
        from app.plc.s7_client import get_s7_client
        client = get_s7_client()
        if not client.is_connected():
            client.connect()
        
        return ApiResponse.ok({
            "success": client.is_connected(),
            "message": "PLC连接成功" if client.is_connected() else "PLC连接失败",
            "plc_ip": settings.plc_ip
        })
    except Exception as e:
        return ApiResponse.fail(f"PLC连接失败: {str(e)}")


# ------------------------------------------------------------
# 5. GET /database - 获取数据库配置
# ------------------------------------------------------------
@router.get("/database")
async def get_database_config():
    """获取数据库配置"""
    return ApiResponse.ok({
        "influxdb": {
            "url": settings.influx_url,
            "org": settings.influx_org,
            "bucket": settings.influx_bucket
            # 不返回token
        }
    })


# ------------------------------------------------------------
# 6. GET /sensors - 获取传感器配置
# ------------------------------------------------------------
@router.get("/sensors")
async def get_sensors_config():
    """获取传感器配置"""
    # TODO: 从数据库读取传感器配置
    sensors = [
        {
            "id": 1,
            "name": "辊道窑温区1",
            "device_type": "roller_kiln",
            "sensor_type": "temperature",
            "db_number": 40,
            "byte_offset": 0,
            "data_type": "REAL"
        },
        {
            "id": 2,
            "name": "辊道窑温区2",
            "device_type": "roller_kiln",
            "sensor_type": "temperature",
            "db_number": 40,
            "byte_offset": 4,
            "data_type": "REAL"
        }
    ]
    return ApiResponse.ok(sensors)
