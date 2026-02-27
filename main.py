# ============================================================
# 文件说明: main.py - FastAPI 应用入口
# ============================================================
# 方法列表:
# 1. create_app()           - 创建FastAPI应用实例
# 2. lifespan()             - 应用生命周期管理
# ============================================================

# [FIX] PyInstaller frozen exe: sys.stdout/stderr 可能为 None
# uvicorn DefaultFormatter 调用 stream.isatty() 会 AttributeError
import sys
import os
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w', encoding='utf-8')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w', encoding='utf-8')

# [CRITICAL] 崩溃防护 - 必须在所有业务 import 之前安装
# 捕获: 未处理异常 / 线程崩溃 / OS 信号 (SIGTERM/SIGINT/SIGBREAK)
from app.core.crash_guard import install as _install_crash_guard
_install_crash_guard()

from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import health, config, hopper, roller, scr_fan, devices, status, export, daily_summary, alarm
from app.routers import websocket as ws_router
from app.core.logging_setup import setup_logging
from app.services.polling_service import start_polling, stop_polling
from app.services.feeding_analysis_service import feeding_analysis_service
from app.services.ws_manager import get_ws_manager
from app.plc.snap7_compat import ensure_snap7_version
from config import get_settings, get_active_env_file

settings = get_settings()
error_log_path = setup_logging()
logger = logging.getLogger(__name__)


# ------------------------------------------------------------
# 1. lifespan() - 应用生命周期管理
# ------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动和关闭时的生命周期管理"""
    # 启动时
    logger.info("[START] 应用启动中...")
    logger.info("[LOG] error 级别日志文件: %s (保留 %d 天)", error_log_path, settings.log_retention_days)
    
    # 1. 加载配置文件
    logger.info("[DATA] 初始化配置...")
    env_file = get_active_env_file()
    if env_file:
        logger.info("[文件] 已加载配置文件: %s", env_file)
    else:
        logger.warning("[配置] 未找到 .env 文件, 使用默认配置和系统环境变量")
    
    logger.info("[INFO] 配置加载完成")

    # 1.05 启动时验证 InfluxDB 连接和认证
    _token_masked = settings.influx_token[:8] + "..." + settings.influx_token[-4:] if len(settings.influx_token) > 12 else "***"
    logger.info("[InfluxDB] URL: %s | Org: %s | Bucket: %s | Token: %s",
                settings.influx_url, settings.influx_org, settings.influx_bucket, _token_masked)
    try:
        from app.core.influxdb import get_influx_client
        _test_client = get_influx_client()
        _buckets = _test_client.buckets_api().find_buckets()
        _bucket_names = [b.name for b in _buckets.buckets] if _buckets and _buckets.buckets else []
        if settings.influx_bucket in _bucket_names:
            logger.info("[InfluxDB] 认证成功, bucket '%s' 存在 (共 %d 个 bucket)", settings.influx_bucket, len(_bucket_names))
        else:
            logger.error("[InfluxDB] 认证成功但 bucket '%s' 不存在! 可用: %s", settings.influx_bucket, _bucket_names)
    except Exception as e:
        logger.error("[InfluxDB] 认证失败! Token 可能无效. 错误: %s", e)
        logger.error("[InfluxDB] 请检查 .env 中的 INFLUX_TOKEN 是否与工控机 InfluxDB 匹配")

    # 1.1 校验 python-snap7 版本（真实 PLC 模式，固定要求 2.0.2）
    if not settings.mock_mode:
        is_valid, message = ensure_snap7_version()
        if not is_valid:
            logger.error(f"[PLC] {message}")
            raise RuntimeError(message)
        logger.info(f"[PLC] {message}")
    
    # 2. 自动迁移 InfluxDB Schema
    logger.info("[DATA] 检查 InfluxDB Schema...")
    from app.core.influx_migration import auto_migrate_on_startup
    if auto_migrate_on_startup():
        logger.info("[INFO] InfluxDB Schema 迁移完成")
    else:
        logger.warning("[WARN] InfluxDB 迁移失败, 但服务继续启动")
    
    # 3. 插入模拟数据（确保 list 接口不为空）
    # [禁止] 暂时禁用：使用手动插入的测试数据
    # print("🌱 初始化模拟数据...")
    # from app.services.data_seeder import seed_mock_data
    # seed_mock_data()
    
    # 4. 启动轮询服务
    # 规则: mock_mode=true 时必须启动轮询，保证 WebSocket 有持续数据源
    should_start_polling = settings.enable_polling or settings.mock_mode

    if should_start_polling:
        await start_polling()
        logger.info("[INFO] 轮询服务已启动")

        # 5. 启动投料分析服务 v6.0 (从 DB 还原投料总量)
        await feeding_analysis_service.restore_from_db()
        logger.info("[Feeding] v6.0 已就绪 (由 polling_service 驱动)")
    else:
        logger.info("[INFO] 轮询服务已禁用 (ENABLE_POLLING=false)")
        logger.info("[INFO] 数据将由外部mock服务提供")

    # 6. 启动 WebSocket 推送任务
    ws_manager = get_ws_manager()
    await ws_manager.start_push_tasks()
    logger.info("[INFO] WebSocket 推送任务已启动")

    yield

    # 关闭时
    logger.info("[STOP] 应用关闭中...")

    # 先停止 WebSocket 推送任务
    await ws_manager.stop_push_tasks()

    if should_start_polling:
        await stop_polling()
    
    # [FIX] 关闭 InfluxDB 客户端
    from app.core.influxdb import close_influx_client
    close_influx_client()
    
    logger.info("[INFO] 所有资源已释放")


# ------------------------------------------------------------
# 2. create_app() - 创建FastAPI应用实例
# ------------------------------------------------------------
def create_app() -> FastAPI:
    """创建并配置FastAPI应用"""
    app = FastAPI(
        title="Ceramic Workshop Backend",
        description="陶瓷车间数字孪生系统后端API",
        version="1.0.0",
        lifespan=lifespan
    )
    
    # CORS 配置 - 允许Flutter前端访问
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 局域网部署，允许所有来源
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # 注册路由
    app.include_router(health.router)
    app.include_router(hopper.router)
    app.include_router(roller.router)
    app.include_router(scr_fan.router)
    app.include_router(devices.router)
    app.include_router(status.router)
    app.include_router(export.router)  # 包含设备运行时长
    app.include_router(daily_summary.router)  # 日汇总数据管理
    app.include_router(config.router, prefix="/api/config", tags=["系统配置"])
    app.include_router(alarm.router)  # 报警管理 (路由自带 /api/alarm 前缀)
    app.include_router(ws_router.router, prefix="/ws", tags=["WebSocket"])
    
    return app


app = create_app()


# [FIX] 自定义 uvicorn log_config：明确禁用颜色，避免 frozen exe 下 isatty() crash
# 根因：uvicorn DefaultFormatter 默认 use_colors=None 时会调用 sys.stdout.isatty()
# PyInstaller 打包后 sys.stdout 可能为 None，导致 AttributeError -> ValueError
_UVICORN_LOG_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "()": "uvicorn.logging.DefaultFormatter",
            "fmt": "%(levelprefix)s %(message)s",
            "use_colors": False,  # 明确 False，不走 isatty() 分支
        },
        "access": {
            "()": "uvicorn.logging.AccessFormatter",
            "fmt": '%(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s',
            "use_colors": False,
        },
    },
    "handlers": {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
        },
        "access": {
            "formatter": "access",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
        },
    },
    "loggers": {
        "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"level": "INFO"},
        "uvicorn.access": {"handlers": ["access"], "level": "INFO", "propagate": False},
    },
}


if __name__ == "__main__":
    # [CRITICAL] 安全检查: 确保 influxdb_client/numpy 可正常导入
    # 防止 numpy .pyc 损坏导致进程卡死在 import 阶段
    from app.core.crash_guard import safe_import_influxdb
    if not safe_import_influxdb(timeout_sec=30):
        print("[ERROR] influxdb_client/numpy 导入异常，已清理缓存，请重新启动")
        sys.exit(1)

    # 1. 委托给托盘应用，行为与打包 exe 完全一致
    #    - PyQt5 系统托盘（绿=运行，红=停止）
    #    - 日志窗口实时追踪 logs/server.log
    #    - 单例保护，防止重复启动
    import sys as _sys
    from pathlib import Path as _Path

    _scripts_dir = _Path(__file__).parent / "scripts"
    if str(_scripts_dir) not in _sys.path:
        _sys.path.insert(0, str(_scripts_dir))

    try:
        from tray_app import run_tray_app
        run_tray_app()
    except ImportError as _e:
        # 2. 降级：PyQt5 / psutil 未安装时，回退到原始 uvicorn 启动
        print(f"[WARN] 托盘模式不可用 ({_e})，以控制台模式启动")
        import uvicorn
        uvicorn.run(
            app,
            host=settings.server_host,
            port=settings.server_port,
            timeout_keep_alive=75,
            proxy_headers=True,
            forwarded_allow_ips="*",
            log_level="debug" if settings.debug else "info",
            log_config=_UVICORN_LOG_CONFIG,
        )

