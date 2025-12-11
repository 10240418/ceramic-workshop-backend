# 数据转换器字段说明文档

## 概述

本文档定义了从 PLC 原始数据转换后存入 InfluxDB 的字段规范。

**数据流**: `PLC原始数据 → Parser解析 → Converter转换 → InfluxDB存储`

---

## 1. 电表模块 (ElectricityMeter)

**转换器**: `converter_elec.py`

### 存储字段

| 字段名 | 显示名称 | 单位 | 数据类型 | 说明 |
|--------|----------|------|----------|------|
| `Pt` | 总有功功率 | kW | float | 直接读取，无需转换 |
| `ImpEp` | 正向有功电能 | kWh | float | 直接读取，无需转换 |
| `Ua_0` | A相电压 | V | float | 直接读取 |
| `Ua_1` | B相电压 | V | float | 直接读取 |
| `Ua_2` | C相电压 | V | float | 直接读取 |
| `I_0` | A相电流 | A | float | 直接读取 |
| `I_1` | B相电流 | A | float | 直接读取 |
| `I_2` | C相电流 | A | float | 直接读取 |

### PLC 原始字段 (供参考，不存储)

- `Uab_0`, `Uab_1`, `Uab_2`: 线电压 (A-B, B-C, C-A)
- `Pa`, `Pb`, `Pc`: 各相有功功率

---

## 2. 流量计模块 (FlowMeter)

**转换器**: `converter_flow.py`

### 存储字段

| 字段名 | 显示名称 | 单位 | 数据类型 | 说明 |
|--------|----------|------|----------|------|
| `flow_rate` | 实时流量 | m³/h | float | 从 RtFlow(L/min) 转换 |
| `total_flow` | 累计流量 | m³ | float | TotalFlow + TotalFlowMilli/1000 |

### 转换公式

```python
# 实时流量: L/min → m³/h
flow_rate = RtFlow / 1000 * 60  # 或 RtFlow * 0.06

# 累计流量: 整数部分 + 小数部分
total_flow = TotalFlow + TotalFlowMilli / 1000.0
```

### PLC 原始字段

| 字段名 | 单位 | 说明 |
|--------|------|------|
| `RtFlow` | L/min | 实时流量原始值 (DWord) |
| `TotalFlow` | m³ | 累计流量整数部分 (DWord) |
| `TotalFlowMilli` | mL | 累计流量小数部分 (Word) |

---

## 3. 温度传感器模块 (TemperatureSensor)

**转换器**: `converter_temp.py`

### 存储字段

| 字段名 | 显示名称 | 单位 | 数据类型 | 说明 |
|--------|----------|------|----------|------|
| `temperature` | 当前温度 | °C | float | 应用 scale 系数后的值 |

### 转换公式

```python
# 如果 PLC 存储的是整数 (scale=0.1)
temperature = raw_value * 0.1

# 如果 PLC 存储的是实际值 (scale=1.0)
temperature = raw_value
```

---

## 4. 称重传感器模块 (WeighSensor)

**转换器**: `converter_weight.py`

### 存储字段

| 字段名 | 显示名称 | 单位 | 数据类型 | 说明 |
|--------|----------|------|----------|------|
| `weight` | 实时重量 | kg | float | 当前净重 |
| `feed_rate` | 下料速度 | kg/s | float | 计算得出 |

### 转换公式

```python
# 实时重量: 优先使用高精度值
weight = NetWeight  # DWord 高精度

# 下料速度: 通过前后重量差计算
# 注意: 下料时重量减少，所以用 previous - current
feed_rate = (previous_weight - current_weight) / interval_seconds

# 示例: 5秒轮询
feed_rate = (weight_5s_ago - weight_now) / 5.0
```

### PLC 原始字段

| 字段名 | 单位 | 说明 |
|--------|------|------|
| `GrossWeight_W` | kg | 毛重 Word 精度 |
| `NetWeight_W` | kg | 净重 Word 精度 |
| `StatusWord` | - | 状态字 |
| `GrossWeight` | kg | 毛重 DWord 高精度 |
| `NetWeight` | kg | 净重 DWord 高精度 |

### 注意事项

1. **下料速度计算需要历史数据**: 转换器需要维护上一次的重量值
2. **首次启动**: 下料速度为 0 (无历史数据)
3. **负值处理**: 如果计算结果为负数，说明在加料，可设为 0 或保留负值表示加料

---

## InfluxDB 存储结构

### Tags (索引字段)

| Tag 名 | 说明 | 示例值 |
|--------|------|--------|
| `device_id` | 设备ID | `short_hopper_1` |
| `device_type` | 设备类型 | `short_hopper` |
| `module_type` | 模块类型 | `ElectricityMeter` |
| `module_tag` | 模块标签 | `electricity` |
| `db_number` | DB块号 | `6` |

### Fields (数值字段)

根据模块类型不同，存储对应的字段（见上述各模块定义）。

---

## 配置文件关系

```
configs/
├── plc_modules.yaml          # 基础模块定义 (字节结构)
├── config_hoppers.yaml       # DB6 料仓设备配置
├── config_roller_kiln.yaml   # DB8 辊道窑设备配置
└── config_scr_fans.yaml      # DB9 SCR/风机设备配置

app/tools/
├── converter_base.py         # 转换器基类
├── converter_elec.py         # 电表转换器
├── converter_flow.py         # 流量计转换器
├── converter_temp.py         # 温度传感器转换器
└── converter_weight.py       # 称重传感器转换器
```

---

## 修改指南

### 如何添加新的存储字段

1. 修改对应的 `converter_xxx.py` 文件
2. 在 `convert()` 方法的返回字典中添加新字段
3. 更新本文档

### 如何修改转换公式

1. 找到对应的转换器文件
2. 修改 `convert()` 方法中的计算逻辑
3. 更新本文档的转换公式说明

---

*最后更新: 2025-12-11*
