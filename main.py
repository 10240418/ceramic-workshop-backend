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

from app.routers import kiln, scr, config, health
from app.services.polling_service import start_polling, stop_polling


# ------------------------------------------------------------
# 1. lifespan() - 应用生命周期管理
# ------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动和关闭时的生命周期管理"""
    # 启动时
    await start_polling()
    yield
    # 关闭时
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
    app.include_router(health.router, prefix="/api", tags=["健康检查"])
    app.include_router(kiln.router, prefix="/api/kiln", tags=["窑炉数据"])
    app.include_router(scr.router, prefix="/api/scr", tags=["SCR设备"])
    app.include_router(config.router, prefix="/api/config", tags=["系统配置"])
    
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
