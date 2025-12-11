# ============================================================
# 文件说明: health.py - 健康检查路由
# ============================================================
# 接口列表:
# 1. GET /health            - 系统健康检查
# 2. GET /health/plc        - PLC连接状态
# 3. GET /health/database   - 数据库连接状态
# ============================================================

from fastapi import APIRouter
from datetime import datetime

from config import get_settings
from app.models.response import ApiResponse

router = APIRouter(prefix="/api", tags=["health"])
settings = get_settings()


# ------------------------------------------------------------
# 1. GET /health - 系统健康检查
# ------------------------------------------------------------
@router.get("/health")
async def health_check():
    """系统健康检查"""
    return ApiResponse.ok({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    })


# ------------------------------------------------------------
# 2. GET /health/plc - PLC连接状态
# ------------------------------------------------------------
# 2. GET /health/plc - PLC连接状态
# ------------------------------------------------------------
@router.get("/health/plc")
async def plc_health():
    """PLC连接状态检查"""
    try:
        from app.plc.s7_client import get_s7_client
        client = get_s7_client()
        
        if not client.is_connected():
            client.connect()
        
        return ApiResponse.ok({
            "connected": client.is_connected(),
            "plc_ip": settings.plc_ip,
            "message": "PLC连接正常" if client.is_connected() else "PLC连接失败"
        })
    except Exception as e:
        return ApiResponse.fail(f"PLC连接检查失败: {str(e)}")


# ------------------------------------------------------------
# 3. GET /health/database - 数据库连接状态
# ------------------------------------------------------------
@router.get("/health/database")
async def database_health():
    """数据库连接状态检查"""
    status = {
        "influxdb": {"connected": False}
    }
    
    # 检查InfluxDB
    try:
        from app.core.influxdb import get_influx_client
        client = get_influx_client()
        health = client.health()
        status["influxdb"]["connected"] = health.status == "pass"
    except Exception as e:
        status["influxdb"]["error"] = str(e)
    
    all_healthy = all(db["connected"] for db in status.values())
    
    return ApiResponse.ok({
        "status": "healthy" if all_healthy else "degraded",
        "databases": status
    })
