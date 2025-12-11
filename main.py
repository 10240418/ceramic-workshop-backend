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

from app.routers import health, config, hopper, roller, scr_fan
from app.services.polling_service import start_polling, stop_polling


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
    
    # 3. 启动轮询服务
    await start_polling()
    
    yield
    
    # 关闭时
    print("🛑 应用关闭中...")
    await stop_polling()


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
    app.include_router(config.router, prefix="/api/config", tags=["系统配置"])
    
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=False)
