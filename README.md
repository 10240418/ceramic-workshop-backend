# Ceramic Workshop Backend

陶瓷车间数字大屏后端 - FastAPI + InfluxDB + S7-1200 PLC

## 快速启动

```bash
# 1. 启动 InfluxDB
docker-compose up -d

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动后端
python3 main.py
```

**访问地址**:
- API 文档: http://localhost:8080/docs
- 健康检查: http://localhost:8080/api/health

## 项目结构

```
ceramic-workshop-backend/
├── main.py                    # 入口 + 生命周期管理
├── config.py                  # 配置 (InfluxDB/PLC地址)
├── docker-compose.yml         # InfluxDB 容器
├── requirements.txt           # Python 依赖
│
├── configs/                   # YAML 配置文件
│   ├── db_mappings.yaml       # DB块映射配置 (动态核心)
│   ├── plc_modules.yaml       # 基础模块定义
│   ├── config_hoppers.yaml    # DB8 料仓设备 (9台)
│   ├── config_roller_kiln.yaml # DB9 辊道窑 (1台)
│   └── config_scr_fans.yaml   # DB10 SCR+风机 (4台)
│
├── app/
│   ├── core/influxdb.py       # InfluxDB 读写
│   ├── plc/
│   │   ├── s7_client.py       # S7-1200 连接
│   │   ├── module_parser.py   # 通用模块解析
│   │   ├── parser_hopper.py
│   │   ├── parser_roller_kiln.py
│   │   └── parser_scr_fan.py
│   ├── services/
│   │   ├── polling_service.py     # 5s轮询→写InfluxDB
│   │   └── history_query_service.py
│   ├── routers/               # API 路由 (按设备分模块)
│   │   ├── health.py          # 健康检查
│   │   ├── config.py          # 系统配置 (CRU)
│   │   ├── hopper.py          # 料仓 API
│   │   ├── roller.py          # 辊道窑 API
│   │   └── scr_fan.py         # SCR/风机 API
│   ├── tools/                 # 数据转换器
│   │   ├── converter_elec.py  # 电表转换
│   │   ├── converter_flow.py  # 流量计转换
│   │   ├── converter_temp.py  # 温度转换
│   │   └── converter_weight.py # 称重转换
│   └── models/                # 响应模型
│
├── scripts/                   # 工具脚本
└── tests/                     # 单元测试
```

## 数据流

```
┌─────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌─────────┐
│  PLC S7-1200 │ → │ Parser 解析  │ → │ Converter    │ → │  InfluxDB    │ → │ REST API │
│  DB8/9/10    │    │ YAML 配置    │    │ 数据转换     │    │  sensor_data │    │ Flutter  │
└─────────────┘    └──────────────┘    └──────────────┘    └──────────────┘    └─────────┘
```

## InfluxDB 存储字段

**Measurement**: `sensor_data`

### Tags (索引)

| Tag          | 说明         |
|--------------|--------------|
| device_id    | 设备ID       |
| device_type  | 设备类型     |
| module_type  | 模块类型     |
| module_tag   | 模块标签     |
| db_number    | PLC DB块号   |

### Fields (按模块类型)

| 模块类型 | 存储字段 | 说明 |
|----------|----------|------|
| **WeighSensor** | `weight`, `feed_rate` | 重量(kg), 下料速度(kg/s) |
| **FlowMeter** | `flow_rate`, `total_flow` | 流量(m³/h), 累计(m³) |
| **TemperatureSensor** | `temperature` | 温度(°C) |
| **ElectricityMeter** | `Pt`, `ImpEp`, `Ua_0~2`, `I_0~2` | 功率、电能、三相电压电流 |

---

## API 端点

### API 列表总览

| 分类 | 方法 | 路径 | 说明 |
|------|------|------|------|
| **健康检查** |
| | GET | `/api/health` | 系统健康状态 |
| | GET | `/api/health/plc` | PLC 连接状态 |
| | GET | `/api/health/database` | 数据库连接状态 |
| **料仓** | 
| | GET | `/api/hopper/list` | 获取料仓列表 |
| | GET | `/api/hopper/{device_id}` | 料仓实时数据 |
| | GET | `/api/hopper/{device_id}/history` | 料仓历史数据 |
| **辊道窑** | 
| | GET | `/api/roller/info` | 辊道窑信息 |
| | GET | `/api/roller/realtime` | 辊道窑实时数据 |
| | GET | `/api/roller/history` | 辊道窑历史数据 |
| | GET | `/api/roller/zone/{zone_id}` | 指定温区数据 |
| **SCR** | 
| | GET | `/api/scr/list` | SCR设备列表 |
| | GET | `/api/scr/{device_id}` | SCR实时数据 |
| | GET | `/api/scr/{device_id}/history` | SCR历史数据 |
| **风机** |
| | GET | `/api/fan/list` | 风机设备列表 |
| | GET | `/api/fan/{device_id}` | 风机实时数据 |
| | GET | `/api/fan/{device_id}/history` | 风机历史数据 |
| **配置** | 
| | GET | `/api/config/server` | 服务器配置 |
| | GET | `/api/config/plc` | PLC配置 |
| | PUT | `/api/config/plc` | 更新PLC配置 |
| | POST | `/api/config/plc/test` | 测试PLC连接 |

---

### 健康检查 API

```bash
# 系统状态
GET /api/health

# PLC连接状态
GET /api/health/plc

# 数据库状态
GET /api/health/database
```

---

### 料仓 API (`/api/hopper`)

```bash
# 获取所有料仓列表
GET /api/hopper/list
GET /api/hopper/list?hopper_type=short_hopper

# 获取料仓实时数据
GET /api/hopper/short_hopper_1

# 获取料仓历史数据
GET /api/hopper/short_hopper_1/history
GET /api/hopper/short_hopper_1/history?module_type=WeighSensor&fields=weight,feed_rate
GET /api/hopper/short_hopper_1/history?start=2025-12-10T00:00:00&end=2025-12-10T12:00:00
```

**料仓类型**:
- `short_hopper`: 短料仓 (4个)
- `no_hopper`: 无料仓 (2个)
- `long_hopper`: 长料仓 (3个)

**返回字段**:
- WeighSensor: `weight`, `feed_rate`
- TemperatureSensor: `temperature`
- ElectricityMeter: `Pt`, `ImpEp`, `Ua_0~2`, `I_0~2`

---

### 辊道窑 API (`/api/roller`)

```bash
# 获取辊道窑信息
GET /api/roller/info

# 获取所有温区实时数据
GET /api/roller/realtime

# 获取历史数据
GET /api/roller/history
GET /api/roller/history?module_type=TemperatureSensor
GET /api/roller/history?zone=zone1&fields=temperature

# 获取指定温区数据
GET /api/roller/zone/zone1
GET /api/roller/zone/zone3
```

**温区**: zone1, zone2, zone3, zone4, zone5, zone6

---

### SCR/风机 API (`/api/scr`, `/api/fan`)

```bash
# SCR设备
GET /api/scr/list
GET /api/scr/scr_1
GET /api/scr/scr_1/history
GET /api/scr/scr_1/history?module_type=FlowMeter&fields=flow_rate

# 风机设备
GET /api/fan/list
GET /api/fan/fan_1
GET /api/fan/fan_1/history?fields=Pt,ImpEp
```

**SCR字段**:
- FlowMeter: `flow_rate`, `total_flow`
- ElectricityMeter: `Pt`, `ImpEp`, `Ua_0~2`, `I_0~2`

**风机字段**:
- ElectricityMeter: `Pt`, `ImpEp`, `Ua_0~2`, `I_0~2`

---

### 配置 API (`/api/config`)

```bash
# 获取服务器配置
GET /api/config/server

# 获取PLC配置
GET /api/config/plc

# 更新PLC配置
PUT /api/config/plc
Content-Type: application/json
{
    "ip_address": "192.168.50.223",
    "poll_interval": 5
}

# 测试PLC连接
POST /api/config/plc/test
```

---

## 设备清单

| DB块   | 设备                    | 模块                  |
|--------|-------------------------|-----------------------|
| DB8    | 4短+2无+3长料仓 (9台)   | 电表+温度+称重        |
| DB9    | 辊道窑 (1台, 6温区)     | 电表+温度             |
| DB10   | 2 SCR + 2 风机 (4台)    | 电表+燃气             |

## 配置文件

### DB块映射 (`configs/db_mappings.yaml`)

```yaml
db_mappings:
  - db_number: 8
    db_name: "DB8_Hoppers"
    total_size: 626
    config_file: "configs/config_hoppers.yaml"
    parser_class: "HopperParser"
    enabled: true

  - db_number: 9
    db_name: "DB9_RollerKiln"
    total_size: 348
    config_file: "configs/config_roller_kiln.yaml"
    parser_class: "RollerKilnParser"
    enabled: true

  - db_number: 10
    db_name: "DB10_SCR_Fans"
    total_size: 244
    config_file: "configs/config_scr_fans.yaml"
    parser_class: "SCRFanParser"
    enabled: true
```

## 环境变量

```bash
# InfluxDB
INFLUX_URL=http://localhost:8086
INFLUX_TOKEN=ceramic-workshop-token
INFLUX_ORG=ceramic-workshop
INFLUX_BUCKET=sensor_data

# PLC
PLC_IP=192.168.50.223
PLC_RACK=0
PLC_SLOT=1
PLC_POLL_INTERVAL=5
```

## 测试

```bash
# 转换器测试
python3 scripts/test_converters.py

# 动态配置测试
python3 scripts/test_dynamic_config.py

# 数据流测试 (需连接PLC)
python3 tests/integration/test_db8_dataflow.py
python3 tests/integration/test_db9_dataflow.py
python3 tests/integration/test_db10_dataflow.py
```

## 故障排查

| 问题 | 解决方案 |
|------|----------|
| PLC连接失败 | 检查 `PLC_IP`，确认网络连通 |
| InfluxDB 写入失败 | 检查 Docker 状态 `docker ps` |
| Address out of range | PLC中对应DB块不存在或大小不足 |

## License

MIT
