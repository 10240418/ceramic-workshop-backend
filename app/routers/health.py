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
import logging

from config import get_settings
from app.models.response import ApiResponse
from app.services.polling_service import get_polling_stats, is_polling_running

logger = logging.getLogger(__name__)

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
        logger.error("[Health] PLC health check failed: %s", e, exc_info=True)
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
    """轮询服务状态检查"""
    try:
        stats = get_polling_stats()
        return ApiResponse.ok({
            "polling_running": is_polling_running(),
            **stats
        })
    except Exception as e:
        logger.error("[Health] polling health check failed: %s", e, exc_info=True)
        return ApiResponse.fail(f"轮询状态检查失败: {str(e)}")


# ------------------------------------------------------------
# 5. GET /health/diagnose - 全面诊断（排查全0数据问题）
# ------------------------------------------------------------
@router.get("/health/diagnose")
async def diagnose_zero_data():
    """全面诊断 - 用于排查 batch API 返回全 0 数据的问题
    
    检查项:
    1. mock_mode 配置
    2. snap7 可用性
    3. PLC 连接状态
    4. 轮询服务状态
    5. 缓存数据状态
    """
    from app.services.polling_service import get_latest_data
    
    issues = []
    
    # 1. 检查 mock_mode
    mock_mode = settings.mock_mode
    
    # 2. 检查 snap7
    try:
        from app.plc.plc_manager import get_plc_manager, SNAP7_AVAILABLE
        snap7_ok = SNAP7_AVAILABLE
    except Exception as e:
        snap7_ok = False
        issues.append(f"snap7导入异常: {e}")
    
    # 3. 检查 PLC 连接
    plc_connected = False
    if not mock_mode:
        try:
            plc = get_plc_manager()
            status = plc.get_status(check_realtime=True)
            plc_connected = status.get("connected", False)
        except Exception as e:
            issues.append(f"PLC状态检查失败: {e}")
    
    # 4. 检查轮询服务
    polling_running = is_polling_running()
    stats = get_polling_stats()
    
    # 5. 检查缓存数据
    cache_data = get_latest_data()
    cache_count = len(cache_data)
    
    # 检查是否有全 0 数据
    zero_data_devices = []
    for device_id, device_data in cache_data.items():
        modules = device_data.get("modules", {})
        for module_tag, module_info in modules.items():
            fields = module_info.get("fields", {})
            if all(v == 0 or v == 0.0 for v in fields.values() if isinstance(v, (int, float))):
                zero_data_devices.append(f"{device_id}.{module_tag}")
    
    # 诊断结论
    if not mock_mode and not snap7_ok:
        issues.append("[ERROR] 关键问题: MOCK_MODE=false 但 snap7 不可用，会导致全 0 数据")
    if not mock_mode and not plc_connected:
        issues.append("[ERROR] PLC 未连接，无法读取真实数据")
    if not polling_running:
        issues.append("[WARN] 轮询服务未运行")
    if cache_count == 0:
        issues.append("[WARN] 缓存为空，可能尚未完成首次轮询")
    if zero_data_devices:
        issues.append(f"[WARN] 发现 {len(zero_data_devices)} 个模块数据全为 0")
    
    return ApiResponse.ok({
        "config": {
            "mock_mode": mock_mode,
            "snap7_available": snap7_ok,
            "plc_ip": settings.plc_ip,
            "poll_interval": settings.plc_poll_interval
        },
        "status": {
            "plc_connected": plc_connected if not mock_mode else "N/A (mock mode)",
            "polling_running": polling_running,
            "total_polls": stats.get("total_polls", 0),
            "devices_in_cache": cache_count
        },
        "zero_data_check": {
            "devices_with_zero_data": zero_data_devices[:10],  # 最多显示 10 个
            "total_zero_count": len(zero_data_devices)
        },
        "issues": issues,
        "recommendation": "切换为 mock 模式: docker compose --profile mock up -d" if issues else "系统正常"
    })


# ------------------------------------------------------------
# 6. GET /health/latest-timestamp - 获取数据库中最新数据的时间戳
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
        logger.error("[Health] get latest timestamp failed: %s", e, exc_info=True)
        return ApiResponse.fail(f"获取最新时间戳失败: {str(e)}")
