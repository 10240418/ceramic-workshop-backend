# ============================================================
# 文件说明: config.py - 系统配置路由
# ============================================================
# 接口列表:
# 1. GET /server            - 获取服务器配置
# 2. GET /plc               - 获取PLC配置
# 3. PUT /plc               - 更新PLC配置 (热更新，无需重启)
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

# 运行时 PLC 配置（支持热更新）
_runtime_plc_config = {
    "ip_address": settings.plc_ip,
    "rack": settings.plc_rack,
    "slot": settings.plc_slot,
    "timeout_ms": settings.plc_timeout,
    "poll_interval": settings.plc_poll_interval
}


def get_runtime_plc_config():
    """获取运行时 PLC 配置"""
    return _runtime_plc_config.copy()


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
    """获取PLC配置（返回运行时配置）"""
    return ApiResponse.ok(get_runtime_plc_config())


# ------------------------------------------------------------
# 3. PUT /plc - 更新PLC配置 (热更新)
# ------------------------------------------------------------
@router.put("/plc")
async def update_plc_config(config: PLCConfigUpdate):
    """更新PLC配置（热更新，无需重启）
    
    修改后立即生效：
    - 更新运行时配置
    - 重置 PLC 客户端连接
    - 下次读取数据时使用新配置
    """
    global _runtime_plc_config
    
    updated_fields = {}
    
    # 更新运行时配置
    if config.ip_address is not None:
        _runtime_plc_config["ip_address"] = config.ip_address
        updated_fields["ip_address"] = config.ip_address
    
    if config.rack is not None:
        _runtime_plc_config["rack"] = config.rack
        updated_fields["rack"] = config.rack
    
    if config.slot is not None:
        _runtime_plc_config["slot"] = config.slot
        updated_fields["slot"] = config.slot
    
    if config.timeout_ms is not None:
        _runtime_plc_config["timeout_ms"] = config.timeout_ms
        updated_fields["timeout_ms"] = config.timeout_ms
    
    if config.poll_interval is not None:
        _runtime_plc_config["poll_interval"] = config.poll_interval
        updated_fields["poll_interval"] = config.poll_interval
    
    # 重置 PLC 客户端，使新配置生效
    if any(k in updated_fields for k in ["ip_address", "rack", "slot", "timeout_ms"]):
        try:
            from app.plc.s7_client import update_s7_client
            update_s7_client(
                ip=_runtime_plc_config["ip_address"],
                rack=_runtime_plc_config["rack"],
                slot=_runtime_plc_config["slot"],
                timeout_ms=_runtime_plc_config["timeout_ms"]
            )
        except Exception as e:
            # 更新失败不影响配置保存
            pass
    
    return ApiResponse.ok({
        "message": "配置更新成功（已立即生效）",
        "updated_fields": updated_fields,
        "current_config": get_runtime_plc_config()
    })


# ------------------------------------------------------------
# 4. POST /plc/test - 测试PLC连接
# ------------------------------------------------------------
@router.post("/plc/test")
async def test_plc_connection():
    """测试PLC连接（使用当前运行时配置）"""
    try:
        from app.plc.s7_client import get_s7_client
        client = get_s7_client()
        if not client.is_connected():
            client.connect()
        
        plc_config = get_runtime_plc_config()
        return ApiResponse.ok({
            "success": client.is_connected(),
            "message": "PLC连接成功" if client.is_connected() else "PLC连接失败",
            "plc_ip": plc_config["ip_address"]
        })
    except Exception as e:
        plc_config = get_runtime_plc_config()
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
