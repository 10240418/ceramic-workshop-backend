# ============================================================
# 文件说明: health.py - 健康检查路由
# ============================================================
# 接口列表:
# 1. GET /health            - 系统健康检查
# 2. GET /health/plc        - PLC连接状态
# 3. GET /health/database   - 数据库连接状态
# 4. GET /health/polling    - 轮询服务状态
# ============================================================

from fastapi import APIRouter
from datetime import datetime

from config import get_settings
from app.models.response import ApiResponse
from app.services.polling_service import get_polling_stats, is_polling_running

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
# 2. GET /health/plc - PLC连接状态（实时检测）
# ------------------------------------------------------------
@router.get("/health/plc")
async def plc_health(probe: bool = True):
    """PLC连接状态检查
    
    Args:
        probe: 是否进行实时探测（默认 True）
               - True: 实时调用 snap7 检测 PLC 是否在线
               - False: 只返回内部状态变量（更快，但可能不准确）
    
    Returns:
        connected: 实时连接状态
        internal_state: 内部状态变量（调试用）
    """
    try:
        from app.plc.plc_manager import get_plc_manager
        plc = get_plc_manager()
        status = plc.get_status(check_realtime=probe)
        
        return ApiResponse.ok({
            "connected": status["connected"],
            "internal_state": status.get("internal_state", status["connected"]),
            "plc_ip": status["ip"],
            "rack": status["rack"],
            "slot": status["slot"],
            "connect_count": status["connect_count"],
            "error_count": status["error_count"],
            "last_error": status["last_error"],
            "last_connect_time": status["last_connect_time"],
            "last_read_time": status["last_read_time"],
            "snap7_available": status["snap7_available"],
            "message": "PLC连接正常" if status["connected"] else "PLC未连接或已断开"
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


# ------------------------------------------------------------
# 4. GET /health/polling - 轮询服务状态
# ------------------------------------------------------------
@router.get("/health/polling")
async def polling_health():
    """轮询服务状态检查
    
    返回:
    - polling_running: 轮询服务是否运行
    - total_polls: 总轮询次数
    - successful_writes: 成功写入次数
    - failed_writes: 写入失败次数
    - cached_points: 缓存的数据点数
    - retry_success: 重试成功次数
    - buffer_size: 当前缓冲区大小
    - batch_size: 批量写入阈值
    - devices_in_cache: 缓存的设备数
    - cache_stats: 本地缓存统计
    - plc_status: PLC 连接状态
    """
    try:
        stats = get_polling_stats()
        return ApiResponse.ok({
            "polling_running": is_polling_running(),
            **stats
        })
    except Exception as e:
        return ApiResponse.fail(f"轮询状态检查失败: {str(e)}")


# ------------------------------------------------------------
# 5. GET /health/latest-timestamp - 获取数据库中最新数据的时间戳
# ------------------------------------------------------------
@router.get("/health/latest-timestamp")
async def get_latest_timestamp():
    """获取数据库中最新数据的时间戳
    
    用于前端确定历史数据查询的时间范围。
    返回数据库中最新写入的数据的时间戳。
    
    Returns:
        timestamp: 最新数据的ISO格式时间戳
        timestamp_utc: UTC时间戳
    """
    try:
        from app.services.history_query_service import HistoryQueryService
        service = HistoryQueryService()
        latest_time = service.get_latest_db_timestamp()
        
        if latest_time:
            return ApiResponse.ok({
                "timestamp": latest_time.isoformat(),
                "timestamp_utc": latest_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "has_data": True
            })
        else:
            return ApiResponse.ok({
                "timestamp": None,
                "timestamp_utc": None,
                "has_data": False,
                "message": "数据库中暂无数据"
            })
    except Exception as e:
        return ApiResponse.fail(f"获取最新时间戳失败: {str(e)}")
