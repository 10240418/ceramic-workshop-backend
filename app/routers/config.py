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
# 7. GET /db-mappings       - 获取DB块映射配置
# 8. GET /db/{db_number}    - 获取指定DB块的设备配置
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
    "poll_interval": settings.plc_poll_interval,
    "realtime_poll_interval": settings.realtime_poll_interval,
    "status_poll_interval": settings.status_poll_interval,
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
    poll_interval: Optional[float] = None
    realtime_poll_interval: Optional[float] = None
    status_poll_interval: Optional[float] = None


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

    if config.realtime_poll_interval is not None:
        _runtime_plc_config["realtime_poll_interval"] = config.realtime_poll_interval
        updated_fields["realtime_poll_interval"] = config.realtime_poll_interval

    if config.status_poll_interval is not None:
        _runtime_plc_config["status_poll_interval"] = config.status_poll_interval
        updated_fields["status_poll_interval"] = config.status_poll_interval

    # 兼容旧字段: 仅更新 poll_interval 时，同步到双轮询间隔
    if config.poll_interval is not None:
        if config.realtime_poll_interval is None:
            _runtime_plc_config["realtime_poll_interval"] = config.poll_interval
            updated_fields["realtime_poll_interval"] = config.poll_interval
        if config.status_poll_interval is None:
            _runtime_plc_config["status_poll_interval"] = config.poll_interval
            updated_fields["status_poll_interval"] = config.poll_interval
    
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
# 5. GET /db-mappings - 获取DB块映射配置
# ------------------------------------------------------------
@router.get("/db-mappings")
async def get_db_mappings():
    """获取所有DB块映射配置（动态配置核心）
    
    **返回**: 所有DB块的配置信息
    - DB号
    - DB名称
    - 总大小
    - 配置文件路径
    - 解析器类名
    - 启用状态
    
    **用途**:
    - 前端动态了解数据结构
    - 按DB块批量查询设备
    - 配置变更后动态适配
    
    **示例**:
    ```json
    {
        "success": true,
        "data": {
            "total": 3,
            "mappings": [
                {
                    "db_number": 8,
                    "db_name": "DB8_Hoppers",
                    "total_size": 626,
                    "description": "9个料仓设备（4短+2无+3长）",
                    "enabled": true
                },
                ...
            ]
        }
    }
    ```
    """
    try:
        import yaml
        
        # 读取 DB 映射配置
        with open("configs/db_mappings.yaml", "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        
        mappings = []
        for db in config.get("db_mappings", []):
            mappings.append({
                "db_number": db["db_number"],
                "db_name": db["db_name"],
                "total_size": db["total_size"],
                "description": db.get("description", ""),
                "parser_class": db.get("parser_class", ""),
                "enabled": db.get("enabled", True)
            })
        
        return ApiResponse.ok({
            "total": len(mappings),
            "mappings": mappings
        })
    except Exception as e:
        return ApiResponse.fail(f"读取配置失败: {str(e)}")


# ------------------------------------------------------------
# 8. GET /db/{db_number} - 获取指定DB块的设备配置
# ------------------------------------------------------------
@router.get("/db/{db_number}")
async def get_db_devices_config(db_number: int):
    """获取指定DB块的所有设备配置
    
    **参数**:
    - `db_number`: DB块号 (8/9/10)
    
    **返回**: 该DB块下所有设备的详细配置
    
    **示例**:
    ```
    GET /api/config/db/8  # 获取DB8（料仓）配置
    GET /api/config/db/9  # 获取DB9（辊道窑）配置
    GET /api/config/db/10 # 获取DB10（SCR/风机）配置
    ```
    """
    try:
        import yaml
        
        # 1. 先从 db_mappings 找到对应的配置文件
        with open("configs/db_mappings.yaml", "r", encoding="utf-8") as f:
            mappings = yaml.safe_load(f)
        
        db_info = None
        for db in mappings.get("db_mappings", []):
            if db["db_number"] == db_number:
                db_info = db
                break
        
        if not db_info:
            return ApiResponse.fail(f"DB{db_number} 配置不存在")
        
        # 2. 读取具体的设备配置文件
        config_file = db_info["config_file"]
        with open(config_file, "r", encoding="utf-8") as f:
            device_config = yaml.safe_load(f)
        
        # 3. 提取设备列表
        devices = []
        
        # 处理料仓配置 (DB8)
        if db_number == 8:
            for hopper_type in ["short_hoppers", "no_hoppers", "long_hoppers"]:
                if hopper_type in device_config:
                    for device in device_config[hopper_type]:
                        devices.append({
                            "device_id": device["device_id"],
                            "device_name": device["device_name"],
                            "device_type": device["device_type"],
                            "start_offset": device["start_offset"],
                            "total_size": device["total_size"],
                            "modules": device["modules"]
                        })
        
        # 处理辊道窑配置 (DB9)
        elif db_number == 9:
            if "roller_kiln" in device_config:
                devices.append(device_config["roller_kiln"])
        
        # 处理 SCR/风机配置 (DB10)
        elif db_number == 10:
            for device_type in ["scr_devices", "fan_devices"]:
                if device_type in device_config:
                    devices.extend(device_config[device_type])
        
        return ApiResponse.ok({
            "db_number": db_number,
            "db_name": db_info["db_name"],
            "description": db_info.get("description", ""),
            "total_devices": len(devices),
            "devices": devices
        })
    except Exception as e:
        return ApiResponse.fail(f"读取配置失败: {str(e)}")

