#!/bin/bash
# ============================================================
# 启动脚本 - 启动后端服务
# ============================================================

set -e

echo "=========================================="
echo "陶瓷车间后端服务启动脚本"
echo "=========================================="

# 检查 Python 环境
if ! command -v python3 &> /dev/null; then
    echo " Python 3 未安装"
    exit 1
fi

# 检查依赖
if [ ! -d "venv" ]; then
    echo "📦 创建虚拟环境..."
    python3 -m venv venv
fi

source venv/bin/activate

echo "📦 安装依赖..."
pip install -r requirements.txt > /dev/null

# 检查 InfluxDB
echo "🔍 检查 InfluxDB 服务..."
if ! docker ps | grep -q ceramic-influxdb; then
    echo " 启动 InfluxDB..."
    docker-compose up -d
    echo "⏳ 等待 InfluxDB 启动..."
    sleep 5
fi

# 启动后端
echo " 启动后端服务..."
echo "=========================================="
uvicorn main:app --reload --host 0.0.0.0 --port 8080
