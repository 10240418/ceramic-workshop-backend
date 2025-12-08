# Ceramic Workshop Backend

陶瓷车间数字孪生系统 - Python FastAPI 后端

## 项目概述

本项目是陶瓷车间数字孪生系统的后端API服务，负责：
- 从PLC采集设备数据（辊道窑、回转窑、SCR设备）
- 存储时序数据到InfluxDB
- 提供RESTful API供Flutter前端调用
- 实时数据轮询与历史数据查询

## 技术栈

- **Framework**: FastAPI 0.109
- **Python**: 3.11+
- **Database**: 
  - InfluxDB 2.7 (时序数据)
  - YAML Files (配置数据)
- **PLC Protocol**: Siemens S7-1200 (python-snap7)
- **Deployment**: Docker Compose

## 快速开始

### 方法 1: 一键启动 (推荐)

**Windows PowerShell:**

```powershell
.\start.ps1
```

此脚本会自动：
1. 检查Docker服务
2. 启动InfluxDB容器
3. 安装Python依赖
4. 启动FastAPI服务

### 方法 2: 手动启动

#### 1. 克隆项目

```bash
git clone <repository-url>
cd ceramic-workshop-backend
```

#### 2. 安装依赖

```bash
pip install -r requirements.txt
```

#### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，配置数据库连接等参数
```

#### 4. 启动数据库 (Docker)

```bash
docker-compose up -d
```

#### 5. 启动后端服务

```bash
# 开发模式 (自动重载)
python quickstart.py

# 或直接使用uvicorn
uvicorn main:app --reload --host 0.0.0.0 --port 8080
```

### 访问服务

- **API文档 (Swagger)**: http://localhost:8080/docs
- **健康检查**: http://localhost:8080/api/health
- **辊道窑实时数据**: http://localhost:8080/api/kiln/roller/realtime

### 测试API

运行API测试脚本：

```bash
python test_api.py
```

## 项目结构

```bash
# 开发模式（支持热重载）
python main.py

# 或使用 uvicorn
uvicorn main:app --reload --host 0.0.0.0 --port 8080
```

### 6. 访问API文档

打开浏览器访问：
- Swagger UI: http://localhost:8080/docs
- ReDoc: http://localhost:8080/redoc

## 项目结构

```
ceramic-workshop-backend/
├── main.py                 # 应用入口
├── config.py               # 配置管理
├── requirements.txt        # Python依赖
├── docker-compose.yml      # Docker编排
├── Dockerfile              # Docker镜像
├── app/
│   ├── models/            # 数据模型
│   │   ├── kiln.py        # 窑炉数据模型
│   │   ├── scr.py         # SCR设备模型
│   │   └── response.py    # 响应模型
│   ├── routers/           # API路由
│   │   ├── health.py      # 健康检查
│   │   ├── kiln.py        # 窑炉接口
│   │   ├── scr.py         # SCR接口
│   │   └── config.py      # 配置接口
│   ├── services/          # 业务服务
│   │   ├── mock_data_service.py      # Mock数据生成
│   │   └── polling_service.py        # 数据轮询
│   └── core/              # 核心工具
│       ├── influxdb.py    # InfluxDB客户端
```

## API 接口

### 健康检查
- `GET /api/health` - 系统健康状态
- `GET /api/health/plc` - PLC连接状态
- `GET /api/health/database` - 数据库状态

### 辊道窑
- `GET /api/kiln/roller/realtime` - 实时数据
- `GET /api/kiln/roller/history` - 历史数据

### 回转窑
- `GET /api/kiln/rotary` - 设备列表
- `GET /api/kiln/rotary/{id}/realtime` - 实时数据
- `GET /api/kiln/rotary/{id}/history` - 历史数据

### SCR设备
- `GET /api/scr` - 设备列表
- `GET /api/scr/{id}/realtime` - 实时数据
- `GET /api/scr/{id}/fans` - 风机数据
- `GET /api/scr/{id}/pumps` - 氨水泵数据
- `GET /api/scr/{id}/gas` - 燃气管路数据

### 系统配置
- `GET /api/config/server` - 服务器配置
- `GET /api/config/plc` - PLC配置
- `GET /api/config/database` - 数据库配置
- `GET /api/config/sensors` - 传感器配置

## 开发模式

项目支持Mock模式，无需实际PLC连接即可开发测试：

```bash
# .env 文件中设置
MOCK_MODE=true
```

Mock模式会生成模拟的设备数据，包括：
- 辊道窑：10个温区 + 能耗数据
- 回转窑：3台设备，每台8个温区 + 下料 + 料仓
- SCR设备：2套设备，风机 + 氨水泵 + 燃气管路

## Docker 部署

### 完整部署（数据库 + 后端）

```bash
docker-compose up -d
```

### 仅部署数据库

```bash
docker-compose up -d influxdb mysql
```

### 查看日志

```bash
docker-compose logs -f backend
```

### 停止服务

```bash
docker-compose down
```

## 数据库管理

### InfluxDB
- Web UI: http://localhost:8086
- 用户名: admin
- 密码: ceramic123
- Organization: ceramic-workshop
- Bucket: sensor_data

## 故障排查

### PLC连接失败
- 检查PLC IP地址配置
- 确认S7-1200参数：Rack=0, Slot=1
- 验证网络连通性

### 数据库连接失败
- 检查Docker容器状态：`docker-compose ps`
- 查看数据库日志：`docker-compose logs influxdb`
- 确认端口未被占用

### 数据未写入InfluxDB
- 检查Mock模式是否开启
- 查看轮询任务日志
- 验证InfluxDB Token配置

## 许可证

MIT License
