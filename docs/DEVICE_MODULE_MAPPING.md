# 设备与模块对应表

## 概览

本项目共有 **14 台设备**，分布在 3 个 PLC DB 块中：

| DB块 | 设备数量 | 设备类型 |
|------|---------|---------|
| DB8 | 9 台 | 料仓 (短料仓、无料仓、长料仓) |
| DB9 | 1 台 | 辊道窑 (6个温区) |
| DB10 | 4 台 | SCR (2台) + 风机 (2台) |

---

## DB8 - 料仓设备 (9台)

### 短料仓 (4台) - 每台 72 字节

| device_id | device_name | module_tag | module_type | 存储字段 |
|-----------|-------------|------------|-------------|----------|
| `short_hopper_1` | 1号短料仓 | `weight` | WeighSensor | weight, feed_rate |
| | | `temp` | TemperatureSensor | temperature |
| | | `meter` | ElectricityMeter | Pt, ImpEp, Ua_0~2, I_0~2 |
| `short_hopper_2` | 2号短料仓 | `weight` | WeighSensor | weight, feed_rate |
| | | `temp` | TemperatureSensor | temperature |
| | | `meter` | ElectricityMeter | Pt, ImpEp, Ua_0~2, I_0~2 |
| `short_hopper_3` | 3号短料仓 | `weight` | WeighSensor | weight, feed_rate |
| | | `temp` | TemperatureSensor | temperature |
| | | `meter` | ElectricityMeter | Pt, ImpEp, Ua_0~2, I_0~2 |
| `short_hopper_4` | 4号短料仓 | `weight` | WeighSensor | weight, feed_rate |
| | | `temp` | TemperatureSensor | temperature |
| | | `meter` | ElectricityMeter | Pt, ImpEp, Ua_0~2, I_0~2 |

### 无料仓 (2台) - 每台 58 字节

| device_id | device_name | module_tag | module_type | 存储字段 |
|-----------|-------------|------------|-------------|----------|
| `no_hopper_1` | 1号无料仓 | `temp` | TemperatureSensor | temperature |
| | | `meter` | ElectricityMeter | Pt, ImpEp, Ua_0~2, I_0~2 |
| `no_hopper_2` | 2号无料仓 | `temp` | TemperatureSensor | temperature |
| | | `meter` | ElectricityMeter | Pt, ImpEp, Ua_0~2, I_0~2 |

### 长料仓 (3台) - 每台 74 字节

| device_id | device_name | module_tag | module_type | 存储字段 |
|-----------|-------------|------------|-------------|----------|
| `long_hopper_1` | 1号长料仓 | `weight` | WeighSensor | weight, feed_rate |
| | | `temp1` | TemperatureSensor | temperature |
| | | `temp2` | TemperatureSensor | temperature |
| | | `meter` | ElectricityMeter | Pt, ImpEp, Ua_0~2, I_0~2 |
| `long_hopper_2` | 2号长料仓 | `weight` | WeighSensor | weight, feed_rate |
| | | `temp1` | TemperatureSensor | temperature |
| | | `temp2` | TemperatureSensor | temperature |
| | | `meter` | ElectricityMeter | Pt, ImpEp, Ua_0~2, I_0~2 |
| `long_hopper_3` | 3号长料仓 | `weight` | WeighSensor | weight, feed_rate |
| | | `temp1` | TemperatureSensor | temperature |
| | | `temp2` | TemperatureSensor | temperature |
| | | `meter` | ElectricityMeter | Pt, ImpEp, Ua_0~2, I_0~2 |

---

## DB9 - 辊道窑 (1台, 12个模块)

### 辊道窑温区结构

| device_id | device_name | module_tag | module_type | 存储字段 | 说明 |
|-----------|-------------|------------|-------------|----------|------|
| `roller_kiln_1` | 辊道窑1号 | `zone1_temp` | TemperatureSensor | temperature | 1号温区温度 |
| | | `zone2_temp` | TemperatureSensor | temperature | 2号温区温度 |
| | | `zone3_temp` | TemperatureSensor | temperature | 3号温区温度 |
| | | `zone4_temp` | TemperatureSensor | temperature | 4号温区温度 |
| | | `zone5_temp` | TemperatureSensor | temperature | 5号温区温度 |
| | | `zone6_temp` | TemperatureSensor | temperature | 6号温区温度 |
| | | `main_meter` | ElectricityMeter | Pt, ImpEp, Ua_0~2, I_0~2 | 主电表 |
| | | `zone1_meter` | ElectricityMeter | Pt, ImpEp, Ua_0~2, I_0~2 | 1号区电表 |
| | | `zone2_meter` | ElectricityMeter | Pt, ImpEp, Ua_0~2, I_0~2 | 2号区电表 |
| | | `zone3_meter` | ElectricityMeter | Pt, ImpEp, Ua_0~2, I_0~2 | 3号区电表 |
| | | `zone4_meter` | ElectricityMeter | Pt, ImpEp, Ua_0~2, I_0~2 | 4号区电表 |
| | | `zone5_meter` | ElectricityMeter | Pt, ImpEp, Ua_0~2, I_0~2 | 5号区电表 |

### 温区 API 映射

| zone_id | 温度模块 | 电表模块 |
|---------|---------|---------|
| `zone1` | zone1_temp | zone1_meter |
| `zone2` | zone2_temp | zone2_meter |
| `zone3` | zone3_temp | zone3_meter |
| `zone4` | zone4_temp | zone4_meter |
| `zone5` | zone5_temp | zone5_meter |
| `zone6` | zone6_temp | (无独立电表) |

---

## DB10 - SCR/风机设备 (4台)

### SCR 设备 (2台) - 每台 66 字节

| device_id | device_name | module_tag | module_type | 存储字段 | 说明 |
|-----------|-------------|------------|-------------|----------|------|
| `scr_1` | 1号SCR | `gas_meter` | FlowMeter | flow_rate, total_flow | 燃气流量 |
| | | `meter` | ElectricityMeter | Pt, ImpEp, Ua_0~2, I_0~2 | 电表 |
| `scr_2` | 2号SCR | `gas_meter` | FlowMeter | flow_rate, total_flow | 燃气流量 |
| | | `meter` | ElectricityMeter | Pt, ImpEp, Ua_0~2, I_0~2 | 电表 |

### 风机设备 (2台) - 每台 56 字节

| device_id | device_name | module_tag | module_type | 存储字段 |
|-----------|-------------|------------|-------------|----------|
| `fan_1` | 1号风机 | `meter` | ElectricityMeter | Pt, ImpEp, Ua_0~2, I_0~2 |
| `fan_2` | 2号风机 | `meter` | ElectricityMeter | Pt, ImpEp, Ua_0~2, I_0~2 |

---

## 模块类型与存储字段对照表

| module_type | 原始字段数 | 存储字段 | 单位 |
|-------------|-----------|----------|------|
| **WeighSensor** | 5 | `weight`, `feed_rate` | kg, kg/s |
| **TemperatureSensor** | 2 | `temperature` | °C |
| **ElectricityMeter** | 14 | `Pt`, `ImpEp`, `Ua_0`, `Ua_1`, `Ua_2`, `I_0`, `I_1`, `I_2` | kW, kWh, V, A |
| **FlowMeter** | 3 | `flow_rate`, `total_flow` | m³/h, m³ |

---

## InfluxDB Tags 说明

每条数据写入 InfluxDB 时包含以下 Tags：

| Tag | 说明 | 示例值 |
|-----|------|--------|
| `device_id` | 设备ID | short_hopper_1, roller_kiln_1, scr_1 |
| `device_type` | 设备类型 | short_hopper, roller_kiln, scr, fan |
| `module_type` | 模块类型 | WeighSensor, TemperatureSensor, ElectricityMeter, FlowMeter |
| `module_tag` | 模块标签 | weight, temp, meter, zone1_temp, gas_meter |
| `db_number` | PLC DB块号 | 8, 9, 10 |

---

## API 查询示例

### 按 device_id 查询

```bash
# 查询短料仓1的实时数据
GET /api/hopper/short_hopper_1

# 查询辊道窑实时数据
GET /api/roller/realtime

# 查询 SCR_1 实时数据
GET /api/scr/scr_1
```

### 按 module_type 查询历史

```bash
# 查询料仓的称重历史
GET /api/hopper/short_hopper_1/history?module_type=WeighSensor

# 查询辊道窑温度历史
GET /api/roller/history?module_type=TemperatureSensor

# 查询 SCR 燃气流量历史
GET /api/scr/scr_1/history?module_type=FlowMeter
```

### 按 zone_id 查询 (仅辊道窑)

```bash
# 查询 zone1 的温度和功率
GET /api/roller/zone/zone1

# 查询 zone3 的历史数据
GET /api/roller/history?zone=zone3
```

---

## 设备总览表

| DB块 | device_id | device_type | 模块数量 | 模块标签列表 |
|------|-----------|-------------|---------|-------------|
| DB8 | short_hopper_1 | short_hopper | 3 | weight, temp, meter |
| DB8 | short_hopper_2 | short_hopper | 3 | weight, temp, meter |
| DB8 | short_hopper_3 | short_hopper | 3 | weight, temp, meter |
| DB8 | short_hopper_4 | short_hopper | 3 | weight, temp, meter |
| DB8 | no_hopper_1 | no_hopper | 2 | temp, meter |
| DB8 | no_hopper_2 | no_hopper | 2 | temp, meter |
| DB8 | long_hopper_1 | long_hopper | 4 | weight, temp1, temp2, meter |
| DB8 | long_hopper_2 | long_hopper | 4 | weight, temp1, temp2, meter |
| DB8 | long_hopper_3 | long_hopper | 4 | weight, temp1, temp2, meter |
| DB9 | roller_kiln_1 | roller_kiln | 12 | zone1~6_temp, main_meter, zone1~5_meter |
| DB10 | scr_1 | scr | 2 | gas_meter, meter |
| DB10 | scr_2 | scr | 2 | gas_meter, meter |
| DB10 | fan_1 | fan | 1 | meter |
| DB10 | fan_2 | fan | 1 | meter |

**总计**: 14 台设备, 46 个模块
