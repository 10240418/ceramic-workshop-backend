# ============================================================
# 文件说明: main.py - FastAPI 应用入口
# ============================================================
# 方法列表:
# 1. create_app()           - 创建FastAPI应用实例
# 2. lifespan()             - 应用生命周期管理
# ============================================================

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import health, config, hopper, roller, scr_fan, devices, status, export, daily_summary
from app.services.polling_service import start_polling, stop_polling
from app.services.feeding_analysis_service import feeding_service
from config import get_settings

settings = get_settings()


# ------------------------------------------------------------
# 1. lifespan() - 应用生命周期管理
# ------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动和关闭时的生命周期管理"""
    # 启动时
    print("🚀 应用启动中...")
    
    # 1. 加载配置文件
    print("📊 初始化配置...")
    print("✅ 配置加载完成")
    
    # 2. 自动迁移 InfluxDB Schema
    print("\n📊 检查 InfluxDB Schema...")
    from app.core.influx_migration import auto_migrate_on_startup
    if auto_migrate_on_startup():
        print("✅ InfluxDB Schema 迁移完成\n")
    else:
        print("⚠️  InfluxDB 迁移失败，但服务继续启动\n")
    
    # 3. 插入模拟数据（确保 list 接口不为空）
    # 🚫 暂时禁用：使用手动插入的测试数据
    # print("🌱 初始化模拟数据...")
    # from app.services.data_seeder import seed_mock_data
    # seed_mock_data()
    
    # 4. 启动轮询服务 (根据环境变量决定是否启用)
    if settings.enable_polling:
        await start_polling()
        print("✅ 轮询服务已启动")
        
        # 5. 启动自动投料分析服务 (6小时执行)
        feeding_service.start()
    else:
        print("ℹ️  轮询服务已禁用 (ENABLE_POLLING=false)")
        print("   数据将由外部mock服务提供")
    
    yield
    
    # 关闭时
    print("🛑 应用关闭中...")
    feeding_service.stop()
    if settings.enable_polling:
        await stop_polling()
    
    # 🔧 关闭 InfluxDB 客户端
    from app.core.influxdb import close_influx_client
    close_influx_client()
    
    # 🔧 关闭本地缓存数据库连接
    from app.core.local_cache import get_local_cache
    get_local_cache().close()
    
    print("✅ 所有资源已释放")


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
    app.include_router(export.router)  # 包含运行时长统计
    app.include_router(daily_summary.router)  # 日汇总数据管理
    app.include_router(config.router, prefix="/api/config", tags=["系统配置"])
    
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    # 🔧 [FIX] 优化的 Uvicorn 配置 - 解决连接断开问题，同时保持容器稳定
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8080,
        timeout_keep_alive=75,  # 关键修复：防止长连接过早断开
        proxy_headers=True,     # 🔧 Docker 环境必需：正确处理反向代理头
        forwarded_allow_ips="*",# 🔧 信任 Docker 网关 IP
        log_level="info"
    )
