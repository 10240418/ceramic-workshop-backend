# Ceramic Workshop Backend

陶瓷车间数字大屏后端 - FastAPI + InfluxDB + S7-1200 PLC

## 快速启动

```bash
docker-compose up -d && pip install -r requirements.txt && python3 main.py
```

**访问**: http://localhost:8080/docs

## 数据流

```
PLC S7-1200 (DB8/9/10) → Parser → Converter → InfluxDB → REST API → Flutter
```

## API 端点

### 核心批量接口 (大屏实时监控用)

| 接口 | 说明 |
|------|------|
| `GET /api/hopper/realtime/batch` | 9个料仓实时数据 |
| `GET /api/roller/realtime/formatted` | 辊道窑6温区实时数据 |
| `GET /api/scr-fan/realtime/batch` | 4个SCR+风机实时数据 |

### 单设备接口

```bash
# 料仓 (short_hopper_1~4, no_hopper_1~2, long_hopper_1~3)
GET /api/hopper/{device_id}
GET /api/hopper/{device_id}/history

# 辊道窑 (zone1~6)
GET /api/roller/realtime
GET /api/roller/zone/{zone_id}
GET /api/roller/history

# SCR/风机 (scr_1~2, fan_1~2)
GET /api/scr/{device_id}
GET /api/fan/{device_id}
GET /api/scr/{device_id}/history
GET /api/fan/{device_id}/history
```

### 健康检查 & 配置

```bash
GET /api/health
GET /api/health/plc
GET /api/config/plc
PUT /api/config/plc
POST /api/config/plc/test
```

## 设备清单

| DB块 | 设备 | 模块 |
|------|------|------|
| DB8 | 9料仓 (4短+2无+3长) | 电表+温度+称重 |
| DB9 | 1辊道窑 (6温区) | 电表+温度 |
| DB10 | 2SCR + 2风机 | 电表+燃气 |

## InfluxDB 字段

| 模块 | 字段 |
|------|------|
| WeighSensor | `weight`, `feed_rate` |
| FlowMeter | `flow_rate`, `total_flow` |
| TemperatureSensor | `temperature` |
| ElectricityMeter | `Pt`, `ImpEp`, `Ua_0`, `I_0`, `I_1`, `I_2` |

## 电流变比说明

电表读取的是电流互感器二次侧数据，需要乘以变比得到一次侧实际电流：

| 设备类型 | 电流变比 | 说明 |
|---------|---------|------|
| 辊道窑 (roller_kiln) | 60 | DB9 中所有电表 |
| 料仓/SCR/风机 | 20 | DB8, DB10 中所有电表 |

**计算公式**: `一次侧电流 = PLC读取值 × 0.1 × 变比`

例如：PLC读取值 = 50
- 辊道窑: 50 × 0.1 × 60 = 300A
- 其他设备: 50 × 0.1 × 20 = 100A

## 环境变量

```bash
INFLUX_URL=http://localhost:8086
INFLUX_TOKEN=ceramic-workshop-token
PLC_IP=192.168.50.223
```

## 故障排查

| 问题 | 解决 |
|------|------|
| PLC连接失败 | 检查 PLC_IP 和网络 |
| InfluxDB失败 | `docker ps` 检查容器 |
| Address out of range | DB块不存在或大小不足 |
