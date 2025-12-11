# Ceramic Workshop Backend

陶瓷车间数字大屏后端 - FastAPI + InfluxDB + S7-1200 PLC

## 核心原则

**奥卡姆剃刀**: 函数 ≤50 行，只实现当前需求，类仅用于状态管理
**动态配置**: 修改配置文件即可，无需改代码

## 快速启动

```bash
docker compose up -d && pip3 install -r requirements.txt && python3 main.py
```

**测试**:

- 完整流程: `python3 scripts/test_complete_flow.py`
- 转换器测试: `python3 scripts/test_converters.py`

## 数据流架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              完整数据流程                                    │
└─────────────────────────────────────────────────────────────────────────────┘

1. PLC读取层 (app/plc/s7_client.py)
   ┌─────────┐
   │ S7-1200 │ ──→ DB8 (料仓) / DB9 (辊道窑) / DB10 (SCR/风机)
   │   PLC   │     读取原始字节数据 (bytes)
   └─────────┘

2. 解析层 (app/plc/parser_*.py)
   ┌─────────────────────┐
   │ parser_hopper.py    │ ──→ 按 config_hoppers.yaml 配置解析
   │ parser_roller_kiln  │ ──→ 按 config_roller_kiln.yaml 配置解析
   │ parser_scr_fan.py   │ ──→ 按 config_scr_fans.yaml 配置解析
   └─────────────────────┘
   输出: 解析后的原始字段 (如 Uab_0, Uab_1, Uab_2, I_0, I_1, I_2...)

3. 转换层 (app/tools/converter_*.py)
   ┌─────────────────────┐
   │ converter_elec.py   │ ──→ 14个电表字段 → 8个精简字段
   │ converter_temp.py   │ ──→ 温度数据转换
   │ converter_weight.py │ ──→ 计算 feed_rate (进料速率)
   │ converter_flow.py   │ ──→ 流量数据转换
   └─────────────────────┘
   输出: 精简后需要存储的字段

4. 存储层 (app/core/influxdb.py → InfluxDB)
   ┌─────────────────────┐
   │     sensor_data     │ ──→ Tags: device_id, device_type, module_type...
   │    (measurement)    │ ──→ Fields: Pt, Ua_0, I_0, temperature, weight...
   └─────────────────────┘

5. API层 (app/routers/*.py → 前端)
   ┌─────────────────────┐
   │ hopper.py           │ ──→ /api/hopper/*   (9个料仓)
   │ roller.py           │ ──→ /api/roller/*   (辊道窑)
   │ scr_fan.py          │ ──→ /api/scr/*, /api/fan/*
   └─────────────────────┘
   为前端提供: 实时数据 + 历史数据查询
```

## 项目结构

```
├── main.py                           # 入口 + 生命周期管理
├── config.py                         # 配置 (InfluxDB/PLC地址)
├── configs/
│   ├── db_mappings.yaml              # DB块映射配置 (动态配置核心)
│   ├── config_hoppers.yaml           # 9料仓: 4短+2无+3长 (DB8)
│   ├── config_roller_kiln.yaml       # 1辊道窑: 6区×(电表+温度) (DB9)
│   ├── config_scr_fans.yaml          # 4设备: 2SCR+2风机 (DB10)
│   └── plc_modules.yaml              # 基础模块定义
├── app/
│   ├── core/influxdb.py              # write_point() / query_data()
│   ├── plc/                          # PLC通信 + 数据解析
│   │   ├── s7_client.py              # S7-1200连接
│   │   ├── parser_hopper.py          # 料仓解析器
│   │   ├── parser_roller_kiln.py     # 辊道窑解析器
│   │   └── parser_scr_fan.py         # SCR/风机解析器
│   ├── tools/                        # 数据转换器 (核心!)
│   │   ├── converter_base.py         # 基类 BaseConverter
│   │   ├── converter_elec.py         # 电表: 14字段→8字段
│   │   ├── converter_temp.py         # 温度传感器
│   │   ├── converter_weight.py       # 称重: 计算feed_rate
│   │   └── converter_flow.py         # 流量计
│   ├── services/
│   │   ├── polling_service.py        # 5s轮询: 解析→转换→存储
│   │   └── history_query_service.py  # 历史数据查询
│   └── routers/                      # API路由 (按设备分类)
│       ├── health.py                 # 健康检查
│       ├── config.py                 # 系统配置
│       ├── hopper.py                 # 料仓API
│       ├── roller.py                 # 辊道窑API
│       └── scr_fan.py                # SCR/风机API
└── scripts/
    ├── test_complete_flow.py         # 完整流程测试
    └── test_converters.py            # 转换器测试
```

## 转换器 (app/tools/)

转换器负责将解析器输出的原始字段**精简**为存储字段：

| 转换器                | 输入字段数 | 输出字段                                   |
| --------------------- | ---------- | ------------------------------------------ |
| `converter_elec.py`   | 14         | Pt, ImpEp, Ua_0, Ua_1, Ua_2, I_0, I_1, I_2 |
| `converter_temp.py`   | 2          | temperature                                |
| `converter_weight.py` | 5          | weight, feed_rate (计算值)                 |
| `converter_flow.py`   | 2          | flow_rate, total_flow                      |

**使用方式**:

```python
from app.tools import get_converter

converter = get_converter("ElectricityMeter")
storage_fields = converter.convert(parsed_data)  # 14字段 → 8字段
```

## InfluxDB 数据模型

**单 measurement**: `sensor_data`

| Tags (索引)                                     | Fields (数值)                                                       |
| ----------------------------------------------- | ------------------------------------------------------------------- |
| device_id, device_type, module_type, module_tag | Pt, ImpEp, Ua_0~2, I_0~2, temperature, weight, feed_rate, flow_rate |

## API 端点

### 料仓 (Hopper)

```
GET /api/hopper/list                # 所有料仓列表
GET /api/hopper/{device_id}         # 单个料仓实时数据
GET /api/hopper/{device_id}/history # 历史数据 (?start=&end=)
```

### 辊道窑 (Roller)

```
GET /api/roller/info                # 辊道窑基本信息
GET /api/roller/realtime            # 所有温区实时数据
GET /api/roller/history             # 历史数据 (?start=&end=)
GET /api/roller/zone/{zone_id}      # 单个温区数据
```

### SCR / 风机

```
GET /api/scr/list                   # SCR列表
GET /api/scr/{device_id}            # SCR实时数据
GET /api/scr/{device_id}/history    # SCR历史数据
GET /api/fan/list                   # 风机列表
GET /api/fan/{device_id}            # 风机实时数据
GET /api/fan/{device_id}/history    # 风机历史数据
```

**返回格式**: `{"success": true, "data": {...}, "error": null}`

## 关键代码示例

```python
# 1. 解析PLC数据
from app.plc.parser_hopper import HopperParser
parser = HopperParser()
parsed_data = parser.parse(plc_bytes)  # 原始字段

# 2. 转换为存储字段
from app.tools import get_converter
converter = get_converter("ElectricityMeter")
storage_fields = converter.convert(parsed_data)  # 精简字段

# 3. 写入InfluxDB
from app.core.influxdb import write_point
write_point("sensor_data",
    tags={"device_id": "short_hopper_1", "module_type": "ElectricityMeter"},
    fields=storage_fields)

# 4. 查询数据 (API层)
from app.services.history_query_service import HistoryQueryService
service = HistoryQueryService()
data = await service.query_device_realtime("short_hopper_1")
```

## 设备清单 (14 台)

| DB 块       | 设备                           | 模块                     |
| ----------- | ------------------------------ | ------------------------ |
| DB8 (554B)  | 4 短料仓 + 2 无料仓 + 3 长料仓 | 电表+温度+称重           |
| DB9 (288B)  | 1 辊道窑 (6 温区)              | 每区: 电表+温度          |
| DB10 (176B) | 2SCR + 2 风机                  | SCR:电表+燃气, 风机:电表 |

**动态配置**: 修改 `configs/db_mappings.yaml` 即可调整 DB 块号，无需改代码

## 基础模块 (plc_modules.yaml)

| 模块              | 大小 | 原始字段                                       | 存储字段 (转换后)        |
| ----------------- | ---- | ---------------------------------------------- | ------------------------ |
| ElectricityMeter  | 40B  | Uab_0~2, Ua_0~2, I_0~2, Pt, ImpEp...           | Pt, ImpEp, Ua_0~2, I_0~2 |
| TemperatureSensor | 8B   | Temperature, SetPoint                          | temperature              |
| WeighSensor       | 14B  | GrossWeigh, TareWeigh, NetWeigh, StatusWord... | weight, feed_rate        |
| GasMeter          | 8B   | GasFlow, GasFlowSpeed                          | flow_rate, total_flow    |

## Windows 下 Docker 部署提示词（离线优先）

如果下次在 Win 上启动后端遇到 python:3.11-slim 拉取/联网超时或 pip 无法访问 PyPI，按下面提示操作：

1) 启动 Docker Desktop 后再动手，`docker ps` 确认 daemon OK。
2) 先在宿主机离线下载 Linux 平台依赖：
   ```powershell
   pip download --platform manylinux2014_x86_64 --python-version 311 --implementation cp --abi cp311 --only-binary=:all: -r requirements.txt -d python_packages_linux
   pip download --platform manylinux2014_x86_64 --python-version 311 --implementation cp --abi cp311 --only-binary=:all: uvloop==0.19.0 -d python_packages_linux
   ```
3) 确保 `Dockerfile` 使用本地离线包目录：
   - `COPY python_packages_linux /app/python_packages`
   - `RUN pip install --no-cache-dir --no-index --find-links=/app/python_packages -r requirements.txt`
4) 构建镜像（不拉取）：
   ```powershell
   docker build --pull=false -t ceramic-backend .
   docker tag ceramic-backend ceramic-workshop-backend-backend:latest
   ```
5) 启动 Compose，跳过拉取和构建：
   ```powershell
   docker compose up --pull never --no-build -d
   ```
6) 验证：`docker ps` 看到 `ceramic-backend` (8080) 与 `ceramic-influxdb` (8086) 运行，即成功。

常见原因与定位：
- 拉取 `python:3.11-slim` 超时：离线预拉并 `--pull=false`/`--no-build`；必要时先 `docker pull python:3.11-slim`。
- pip 走代理/被拦：用步骤 2 的离线包 + `--no-index`，避免联网。
- 找不到镜像名：给本地镜像补 tag `ceramic-workshop-backend-backend:latest` 后再 `docker compose up --pull never --no-build -d`。

## 避坑指南

1. **添加设备**: 改 YAML 配置，不改 Parser 代码
2. **修改 DB 块号**: 修改 `configs/db_mappings.yaml`，重启服务即可
3. **字节序**: S7 用大端 `struct.unpack('>'...)`
4. **偏移量**: 单位是字节，DB8.14 = 第 14 字节
5. **InfluxDB**: Tags 可索引，Fields 可聚合
6. **转换器**: 新增模块类型时，需在 `app/tools/` 添加对应转换器

## 开发流程

1. **添加新设备类型**:

   - 在 `configs/` 添加配置文件
   - 在 `app/plc/` 添加解析器
   - 在 `app/tools/` 添加转换器
   - 在 `app/routers/` 添加 API 路由

2. **测试验证**:
   ```bash
   python3 scripts/test_converters.py      # 测试转换器
   python3 scripts/test_complete_flow.py   # 测试完整流程
   python3 main.py                         # 启动服务
   ```

---

中文回答我.
命令行使用 python3 main.py 启动服务。
你的命令行每次都需要在新的窗口执行命令,如果我已经运行了python main.py的话.
