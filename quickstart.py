# ============================================================
# 快速启动脚本 - 用于开发环境快速测试
# ============================================================
# 使用方法:
# 1. 确保安装依赖: pip install -r requirements.txt
# 2. 启动Docker服务: docker-compose up -d
# 3. 运行此脚本: python quickstart.py
# ============================================================

import asyncio
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import app
import uvicorn


async def check_services():
    """检查必要服务是否运行"""
    print("\n🔍 检查服务状态...")
    
    # 检查InfluxDB
    try:
        from app.core.influxdb import get_influx_client
        client = get_influx_client()
        print("✅ InfluxDB连接成功")
    except Exception as e:
        print(f"❌ InfluxDB连接失败: {e}")
        print("提示: 请运行 'docker-compose up -d' 启动InfluxDB")
        return False
    
    return True


def main():
    """主函数"""
    print("=" * 60)
    print("   陶瓷车间数字孪生系统 - 后端快速启动")
    print("=" * 60)
    
    # 检查服务
    if not asyncio.run(check_services()):
        print("\n⚠️  服务检查失败，请先启动必要的服务")
        sys.exit(1)
    
    # 初始化数据库
    # 启动服务器
    print("\n🚀 启动FastAPI服务器...")
    print(f"📍 API文档地址: http://localhost:8080/docs")
    print(f"📍 健康检查: http://localhost:8080/api/health")
    print(f"📍 PLC地址: {os.getenv('PLC_IP', '192.168.50.223')}")
    print("\n按 Ctrl+C 停止服务器\n")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
        log_level="info"
    )


if __name__ == "__main__":
    main()
