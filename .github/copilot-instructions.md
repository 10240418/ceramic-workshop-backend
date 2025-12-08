# Ceramic Workshop Backend - AI Coding Instructions

> **Reading Priority for AI:**
>
> 1. **[CRITICAL]** - Hard constraints, must strictly follow
> 2. **[IMPORTANT]** - Key specifications
> 3. Other content - Reference information

---

## 0. [CRITICAL] Core Development Principles

### 0.1 开发者背景

- **个人开发者**：独立完成后端和前端全部开发
- **业务优先**：以实现业务功能为第一目标，避免过度设计

### 0.2 奥卡姆剃刀原则 (Occam's Razor)

> **如无必要，勿增实体** - 最简单的解决方案往往是最好的

- **[CRITICAL]** 代码精简：不写冗余代码，每一行都有存在的意义
- **[CRITICAL]** 避免过度抽象：不为可能的未来需求提前设计
- **[CRITICAL]** 减少依赖：只引入必要的第三方库
- **[CRITICAL]** 功能聚焦：每个模块只做一件事，做好这件事

### 0.3 代码文件结构规范

> **[CRITICAL]** 所有代码文件必须遵循以下注释规范，提高可读性

**文件头部方法索引：**

```python
# ============================================================
# 文件说明: xxx_service.py - XXX业务服务层
# ============================================================
# 方法列表:
# 1. get_realtime_data()    - 获取实时数据
# 2. get_history_data()     - 获取历史数据
# 3. start_polling()        - 启动轮询任务
# 4. _parse_plc_data()      - [私有] 解析PLC数据
# ============================================================
```

**方法实现注释：**

```python
# ------------------------------------------------------------
# 1. get_realtime_data() - 获取实时数据
# ------------------------------------------------------------
def get_realtime_data(self, device_id: int) -> Dict[str, Any]:
    """获取指定设备的实时数据"""
    pass

# ------------------------------------------------------------
# 2. get_history_data() - 获取历史数据
# ------------------------------------------------------------
def get_history_data(self, device_id: int, start: datetime, end: datetime) -> List[Dict]:
    """查询指定时间范围的历史数据"""
    pass
```

### 0.4 精简代码准则

- **不要**：写未使用的代码、过度封装、提前优化
- **要做**：直接实现业务逻辑、代码自文档化、必要时才抽象
- **函数**：单一职责，长度控制在 50 行以内
- **类**：只有在确实需要状态管理时才使用类

---

## 1. Project Overview

| Property         | Value                                                           |
| ---------------- | --------------------------------------------------------------- |
| **Type**         | Industrial IoT Backend API Service                              |
| **Stack**        | Python 3.11+ / FastAPI / python-snap7                           |
| **Architecture** | Layered: Models → Services → Routers (Controllers)              |
| **Database**     | InfluxDB (Time-series) + YAML Files (Config)                    |
| **Protocol**     | Siemens S7-1200 PLC (python-snap7, ⭐757 stars, best ecosystem) |
| **Deployment**   | Docker Compose (Local Industrial Control PC)                    |

---

## 2. System Architecture

### 2.1 Deployment Topology

```
┌─────────────────────── Industrial Control PC ───────────────────────┐
│                                                                      │
│  ┌──────────────┐      ┌──────────────┐      ┌──────────────┐       │
│  │  Flutter App │ HTTP │Python Backend│      │   Docker     │       │
│  │  (Frontend)  │ ───► │  (FastAPI)   │ ───► │  InfluxDB    │       │
│  └──────────────┘      └──────┬───────┘      │  (仅此一个)  │       │
│         ▲                     │              └──────────────┘       │
│         │                     │ S7 Protocol (python-snap7)          │
│         │                     │ YAML Config (configs/*.yaml)        │
│     localhost                 ▼                                     │
└───────────────────────────────┼─────────────────────────────────────┘
                                │
                                ▼
                         ┌──────────────┐
                         │     PLC      │
                         │   S7-1200    │
                         └──────────────┘
```

### 2.2 Data Flow

```
PLC ──(S7协议)──► Python Backend ──(写入)──► InfluxDB (时序数据)
     每5秒轮询         │                         │
   python-snap7        │                         ▼
                       │                 Historical Query
                       │
                       ├──(读取配置)──► YAML Files (configs/)
                       │                 - devices.yaml
                       │                 - sensors.yaml
                       ▼
                  Flutter App ◄──(REST API)── Real-time + History
```

---

## 3. [CRITICAL] Project Structure

```
ceramic-workshop-backend/
├── main.py              # App entry, uvicorn startup
├── config.py            # Configuration management (pydantic-settings)
├── dependencies.py      # Dependency injection (FastAPI Depends)
├── requirements.txt     # Python dependencies
├── pyproject.toml       # Project metadata (optional)
├── configs/
│   └── config.yaml      # Configuration file (DB, PLC addresses)
├── app/
│   ├── __init__.py
│   ├── models/          # Data models (Pydantic + SQLAlchemy)
│   │   ├── __init__.py
│   │   ├── base.py              # Base model (ID, timestamps)
│   │   ├── kiln.py              # Kiln data models
│   │   ├── scr.py               # SCR equipment models
│   │   └── sensor.py            # Sensor config models
│   ├── services/        # Business logic layer
│   │   ├── __init__.py
│   │   ├── plc_service.py       # PLC communication (python-snap7)
│   │   ├── kiln_service.py      # Kiln business service
│   │   ├── scr_service.py       # SCR business service
│   │   └── influx_service.py    # InfluxDB service
│   ├── routers/         # API routers (controllers)
│   │   ├── __init__.py
│   │   ├── kiln.py              # Kiln endpoints
│   │   ├── scr.py               # SCR endpoints
│   │   ├── config.py            # Config endpoints
│   │   └── health.py            # Health check
│   ├── core/            # Core utilities
│   │   ├── __init__.py
│   │   ├── database.py          # MySQL connection (SQLAlchemy)
│   │   ├── influxdb.py          # InfluxDB client
│   │   └── exceptions.py        # Custom exceptions
│   ├── plc/             # PLC communication module
│   │   ├── __init__.py
│   │   ├── s7_client.py         # S7 protocol client (python-snap7)
│   │   └── data_parser.py       # Data parsing (Big Endian, snap7.util)
│   └── utils/           # Utility functions
│       ├── __init__.py
│       ├── response.py          # Standard response format
│       └── pagination.py        # Pagination helper
├── tests/               # Unit tests (pytest)
│   ├── __init__.py
│   ├── test_plc_service.py
│   └── test_kiln_service.py
├── docker-compose.yml   # InfluxDB + Backend deployment
└── Dockerfile           # Python container image
```

---

## 4. [CRITICAL] Functional Requirements

### 4.1 辊道窑 (Roller Kiln) 功能需求

#### 4.1.1 温度采集、分区显示

| 功能项           | 描述                                                 | 刷新频率   |
| ---------------- | ---------------------------------------------------- | ---------- |
| 2D/3D 可视化模型 | 提供辊道窑二维或三维数字孪生模型，清晰展示各分区结构 | -          |
| 分区温度显示     | 模型上实时显示各分区当前温度数值                     | ≤5 秒      |
| 文字+图标展示    | 每个区域以文字和温度图标组合方式展示实时温度         | -          |
| 实时温度更新     | 温度数据与 PLC/传感器实时同步                        | 延迟 ≤3 秒 |
| 历史温度曲线     | 支持查询并以曲线图展示各区域历史温度变化趋势         | -          |

#### 4.1.2 能耗采集、显示

| 功能项        | 描述                                            | 刷新频率 |
| ------------- | ----------------------------------------------- | -------- |
| 实时能耗数据  | 系统实时采集并显示设备总能耗                    | ≤5 秒    |
| 文字+图标展示 | 以文字数值+能耗趋势图表方式直观展示当前能耗状态 | -        |
| 单位标注      | 明确标注能耗单位（V、A、kW）                    | -        |

#### 4.1.3 历史数据查询

| 功能项       | 描述                               |
| ------------ | ---------------------------------- |
| 时间范围选择 | 支持自定义起止时间查询历史能耗数据 |
| 数据图表展示 | 以折线图等方式展示历史能耗趋势     |

---

### 4.2 回转窑 (Rotary Kiln) 功能需求

#### 4.2.1 温度采集、分区显示

| 功能项           | 描述                                                 | 刷新频率   |
| ---------------- | ---------------------------------------------------- | ---------- |
| 2D/3D 可视化模型 | 提供回转窑二维或三维数字孪生模型，清晰展示各分区结构 | -          |
| 分区温度显示     | 模型上实时显示各分区当前温度数值（8 个温区）         | ≤5 秒      |
| 文字+图标展示    | 每个区域以文字和温度图标组合方式展示实时温度         | -          |
| 实时温度更新     | 温度数据与 PLC/传感器实时同步                        | 延迟 ≤3 秒 |
| 历史温度曲线     | 支持查询并以曲线图展示各区域历史温度变化趋势         | -          |

#### 4.2.2 能耗采集、显示

| 功能项        | 描述                                            | 刷新频率 |
| ------------- | ----------------------------------------------- | -------- |
| 实时能耗数据  | 系统实时采集并显示设备总能耗                    | ≤5 秒    |
| 文字+图标展示 | 以文字数值+能耗趋势图表方式直观展示当前能耗状态 | -        |
| 单位标注      | 明确标注能耗单位（V、A、kW）                    | -        |

#### 4.2.3 下料速度显示

| 功能项        | 描述                             | 刷新频率 |
| ------------- | -------------------------------- | -------- |
| 实时速度显示  | 实时显示当前下料速度数值（kg/h） | ≤5 秒    |
| 文字+图标展示 | 以数值+速度指示图标方式展示      | -        |
| 速度曲线      | 以动态曲线展示下料速度变化趋势   | -        |

#### 4.2.4 料仓重量显示

| 功能项        | 描述                                        | 刷新频率 |
| ------------- | ------------------------------------------- | -------- |
| 实时重量显示  | 实时显示各料仓当前重量                      | ≤5 秒    |
| 文字+图标展示 | 以数值+料仓图示方式展示，图示可映射料位高低 | -        |
| 容量百分比    | 显示当前重量占料仓总容量的百分比            | -        |
| 重量告警      | 料仓重量低于下限时触发告警                  | -        |

#### 4.2.5 历史数据查询

| 功能项        | 描述                                             |
| ------------- | ------------------------------------------------ |
| 时间范围选择  | 支持自定义起止时间查询历史下料速度和料仓重量数据 |
| 多维度查询    | 支持按小时、日、周、月等维度查询                 |
| 曲线/表格展示 | 以曲线图或数据表格展示历史变化趋势               |

---

### 4.3 SCR 设备 (SCR Equipment) 功能需求

#### 4.3.1 风机能耗采集、显示

| 功能项        | 描述                                  | 刷新频率 |
| ------------- | ------------------------------------- | -------- |
| 实时风机能耗  | 实时显示各风机当前功率和累计电量      | ≤5 秒    |
| 多风机显示    | 若有多台风机，需分别显示各风机能耗    | -        |
| 文字+图标展示 | 以数值+风机图标方式展示运行状态和能耗 | -        |
| 运行状态      | 显示风机启停状态（运行/停止）         | -        |
| 能耗统计      | 支持查看风机日/月/年累计能耗          | -        |

#### 4.3.2 氨水泵能耗采集、显示

| 功能项        | 描述                                  | 刷新频率 |
| ------------- | ------------------------------------- | -------- |
| 实时水泵能耗  | 实时显示各水泵当前功率和累计电量      | ≤5 秒    |
| 文字+图标展示 | 以数值+水泵图标方式展示运行状态和能耗 | -        |
| 运行状态      | 显示水泵启停状态（运行/停止）         | -        |
| 能耗统计      | 支持查看水泵日/月/年累计能耗          | -        |

#### 4.3.3 燃气用量采集

| 功能项        | 描述                              | 刷新频率 |
| ------------- | --------------------------------- | -------- |
| 实时燃气流速  | 实时显示 2 条燃气管路当前流速     | ≤5 秒    |
| 文字+图标展示 | 以数值+图表方式展示运行状态和能耗 | -        |
| 能耗统计      | 支持查看燃气日/月/年累计消耗      | -        |

#### 4.3.4 历史数据查询

| 功能项       | 描述                                      |
| ------------ | ----------------------------------------- |
| 时间范围选择 | 支持自定义起止时间查询风机和水泵历史能耗  |
| 设备选择     | 支持选择单台或多台设备进行对比查询        |
| 多维度统计   | 支持按小时、日、周、月、年等维度统计      |
| 图表展示     | 以柱状图/折线图展示历史能耗趋势和设备对比 |

---

### 4.4 系统配置 (System Configuration)

| 功能项         | 描述                                                        |
| -------------- | ----------------------------------------------------------- |
| 服务器地址配置 | 支持设置和修改服务器 IP 地址和端口号                        |
| PLC 地址配置   | 支持设置和修改 PLC 设备的 IP 地址、端口及通信协议参数       |
| 数据库地址配置 | 支持设置和修改数据库连接地址、端口、用户名、密码            |
| 传感器地址配置 | 支持批量或单独设置各传感器的通信地址（Modbus 地址、点位等） |
| 配置验证       | 修改配置后系统自动测试连接有效性并反馈结果                  |
| 配置保存       | 配置修改后可保存，系统重启后配置依然生效                    |
| 权限控制       | 配置功能需管理员权限才能访问和修改                          |

---

## 5. Equipment Data Model

### 5.1 Roller Kiln (辊道窑)

```python
from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional

class ZoneTemp(BaseModel):
    """温区温度数据"""
    zone_id: int             # 温区ID
    zone_name: str           # 温区名称
    temperature: float       # 温度 °C
    set_point: Optional[float] = None  # 设定温度 °C

class RollerKilnRealtime(BaseModel):
    """辊道窑实时数据"""
    timestamp: datetime
    zones: List[ZoneTemp]    # 多温区温度数据
    voltage: float           # 电压 V
    current: float           # 电流 A
    power: float             # 功率 kW
    total_energy: float      # 累计电量 kWh
    status: bool             # 运行状态

class RollerKilnHistory(BaseModel):
    """辊道窑历史数据查询响应"""
    start_time: datetime
    end_time: datetime
    interval: str            # 数据间隔: 5s, 1m, 5m, 1h, 1d
    data: List[RollerKilnRealtime]
```

### 5.2 Rotary Kiln (回转窑)

```python
from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional

class HopperData(BaseModel):
    """料仓数据"""
    hopper_id: int           # 料仓ID
    weight: float            # 当前重量 kg
    capacity: float          # 总容量 kg
    percent: float           # 容量百分比 %
    low_alarm: bool          # 低重量告警状态
    alarm_threshold: float   # 告警阈值 kg

class RotaryKilnRealtime(BaseModel):
    """回转窑实时数据"""
    timestamp: datetime
    device_id: int           # 设备ID 1-3
    device_name: str         # 设备名称
    zones: List[ZoneTemp]    # 8温区温度数据
    voltage: float           # 电压 V
    current: float           # 电流 A
    power: float             # 功率 kW
    total_energy: float      # 累计电量 kWh
    feed_speed: float        # 下料速度 kg/h
    hopper: HopperData       # 料仓数据
    status: bool             # 运行状态

class RotaryKilnHistory(BaseModel):
    """回转窑历史数据查询响应"""
    device_id: int
    start_time: datetime
    end_time: datetime
    interval: str            # 数据间隔
    dimension: str           # 查询维度: hour, day, week, month
    data: List[RotaryKilnRealtime]
```

### 5.3 SCR Equipment (SCR 设备)

```python
from pydantic import BaseModel
from datetime import datetime
from typing import List

class FanData(BaseModel):
    """风机数据"""
    fan_id: int              # 风机ID
    fan_name: str            # 风机名称
    power: float             # 功率 kW
    cumulative_energy: float # 累计电量 kWh
    daily_energy: float      # 日累计电量 kWh
    monthly_energy: float    # 月累计电量 kWh
    yearly_energy: float     # 年累计电量 kWh
    status: bool             # 运行状态 (true=运行, false=停止)

class PumpData(BaseModel):
    """氨水泵数据"""
    pump_id: int             # 水泵ID
    pump_name: str           # 水泵名称
    power: float             # 功率 kW
    cumulative_energy: float # 累计电量 kWh
    daily_energy: float      # 日累计电量 kWh
    monthly_energy: float    # 月累计电量 kWh
    yearly_energy: float     # 年累计电量 kWh
    status: bool             # 运行状态 (true=运行, false=停止)

class GasPipelineData(BaseModel):
    """燃气管路数据"""
    pipeline_id: int         # 管路ID (1 或 2)
    pipeline_name: str       # 管路名称
    flow_rate: float         # 当前流速 m³/h
    cumulative_volume: float # 累计用量 m³
    daily_volume: float      # 日累计用量 m³
    monthly_volume: float    # 月累计用量 m³
    yearly_volume: float     # 年累计用量 m³

class SCRRealtime(BaseModel):
    """SCR设备实时数据"""
    timestamp: datetime
    device_id: int           # 设备ID 1-2
    device_name: str         # 设备名称
    fans: List[FanData]      # 风机数据列表
    ammonia_pumps: List[PumpData]  # 氨水泵数据列表
    gas_pipelines: List[GasPipelineData]  # 2条燃气管路数据
    status: bool             # 设备总运行状态

class SCRHistory(BaseModel):
    """SCR设备历史数据查询响应"""
    device_ids: List[int]    # 查询的设备ID列表
    start_time: datetime
    end_time: datetime
    dimension: str           # 查询维度: hour, day, week, month, year
    data: List[SCRRealtime]
```

### 5.4 Alarm Model (告警模型)

```python
from pydantic import BaseModel
from datetime import datetime
from enum import Enum
from typing import Optional

class AlarmLevel(str, Enum):
    """告警级别"""
    INFO = "info"            # 信息
    WARNING = "warning"      # 警告
    CRITICAL = "critical"    # 严重

class AlarmType(str, Enum):
    """告警类型"""
    HOPPER_LOW_WEIGHT = "hopper_low_weight"     # 料仓低重量
    TEMP_DEVIATION = "temp_deviation"            # 温度偏差
    COMMUNICATION_LOST = "communication_lost"    # 通信丢失
    EQUIPMENT_FAULT = "equipment_fault"          # 设备故障

class Alarm(BaseModel):
    """告警记录"""
    alarm_id: int
    timestamp: datetime
    device_type: str         # roller_kiln, rotary_kiln, scr
    device_id: int
    alarm_type: AlarmType
    alarm_level: AlarmLevel
    message: str
    value: Optional[float]   # 触发告警的值
    threshold: Optional[float]  # 告警阈值
    acknowledged: bool       # 是否已确认
    acknowledged_at: Optional[datetime]
    resolved: bool           # 是否已解决
    resolved_at: Optional[datetime]
```

---

## 6. [CRITICAL] API Endpoints Design

### 6.1 Real-time Data API

```http
# 辊道窑
GET /api/kiln/roller/realtime              # 辊道窑实时数据

# 回转窑 (3台设备)
GET /api/kiln/rotary                       # 所有回转窑列表
GET /api/kiln/rotary/:id/realtime          # 回转窑实时数据 (id: 1-3)

# SCR设备 (2套设备)
GET /api/scr                               # 所有SCR设备列表
GET /api/scr/:id/realtime                  # SCR实时数据 (id: 1-2)
GET /api/scr/:id/fans                      # SCR风机数据
GET /api/scr/:id/pumps                     # SCR氨水泵数据
GET /api/scr/:id/gas                       # SCR燃气管路数据

# 系统健康检查
GET /api/health                            # 健康检查
GET /api/health/plc                        # PLC连接状态
GET /api/health/database                   # 数据库连接状态
```

### 6.2 Historical Data API

```http
# 辊道窑历史数据
GET /api/kiln/roller/history
    ?start={ISO8601}
    &end={ISO8601}
    &interval={5s|1m|5m|1h|1d}
    &zone_ids={1,2,3}                         # 可选，指定温区

# 回转窑历史数据
GET /api/kiln/rotary/:id/history
    ?start={ISO8601}
    &end={ISO8601}
    &interval={5s|1m|5m|1h|1d}
    &dimension={hour|day|week|month}
    &data_type={temperature|energy|feed|hopper}  # 数据类型筛选

# SCR历史数据
GET /api/scr/:id/history
    ?start={ISO8601}
    &end={ISO8601}
    &dimension={hour|day|week|month|year}
    &equipment_type={fans|pumps|gas|all}

# SCR多设备对比查询
GET /api/scr/compare
    ?device_ids={1,2}
    &start={ISO8601}
    &end={ISO8601}
    &dimension={hour|day|week|month|year}
```

### 6.3 Statistics API (能耗统计)

```http
# SCR风机能耗统计
GET /api/scr/:id/fans/:fan_id/statistics
    ?period={daily|monthly|yearly}

# SCR氨水泵能耗统计
GET /api/scr/:id/pumps/:pump_id/statistics
    ?period={daily|monthly|yearly}

# SCR燃气用量统计
GET /api/scr/:id/gas/:pipeline_id/statistics
    ?period={daily|monthly|yearly}

# 设备能耗汇总
GET /api/statistics/energy
    ?device_type={roller_kiln|rotary_kiln|scr}
    &period={daily|monthly|yearly}
```

### 6.4 Alarm API (告警接口)

```http
GET  /api/alarms                           # 获取告警列表
GET  /api/alarms/active                    # 获取活跃告警
GET  /api/alarms/:id                       # 获取告警详情
POST /api/alarms/:id/acknowledge           # 确认告警
POST /api/alarms/:id/resolve               # 解决告警
GET  /api/alarms/history                   # 历史告警查询
    ?start={ISO8601}
    &end={ISO8601}
    &device_type={roller_kiln|rotary_kiln|scr}
    &level={info|warning|critical}
```

### 6.5 Configuration API (配置接口)

```http
# 服务器配置
GET  /api/config/server                    # 获取服务器配置
PUT  /api/config/server                    # 更新服务器配置

# PLC配置
GET  /api/config/plc                       # 获取PLC配置
PUT  /api/config/plc                       # 更新PLC配置
POST /api/config/plc/test                  # 测试PLC连接

# 数据库配置
GET  /api/config/database                  # 获取数据库配置
PUT  /api/config/database                  # 更新数据库配置
POST /api/config/database/test             # 测试数据库连接

# 传感器配置
GET  /api/config/sensors                   # 获取所有传感器配置
GET  /api/config/sensors/:id               # 获取单个传感器配置
PUT  /api/config/sensors/:id               # 更新单个传感器配置
PUT  /api/config/sensors/batch             # 批量更新传感器配置
POST /api/config/sensors/validate          # 验证传感器配置

# 配置导入导出
GET  /api/config/export                    # 导出所有配置
POST /api/config/import                    # 导入配置
```

### 6.6 Authentication API (认证接口)

```http
POST /api/auth/login                       # 管理员登录
POST /api/auth/logout                      # 登出
GET  /api/auth/me                          # 获取当前用户信息
PUT  /api/auth/password                    # 修改密码
```

---

## 7. [CRITICAL] PLC Communication

### 7.1 S7 Protocol Configuration

```yaml
PLC Config:
  IP: 192.168.0.1
  Rack: 0
  Slot: 1
  Timeout: 5s
# [CRITICAL] S7-1200 固定参数
# Rack = 0, Slot = 1
```

### 7.2 Data Types & Byte Order

```python
import struct
import snap7.util as s7util

# [CRITICAL] S7 Data Types - All use Big Endian
# BOOL, BYTE, WORD, DWORD, INT, DINT, REAL

# Parse REAL (32-bit float) - using snap7.util
def parse_real(data: bytes, offset: int) -> float:
    """Parse S7 REAL (Big Endian 4-byte float)"""
    return s7util.get_real(data, offset)

# Parse INT (16-bit signed integer)
def parse_int(data: bytes, offset: int) -> int:
    """Parse S7 INT (Big Endian 2-byte signed int)"""
    return s7util.get_int(data, offset)

# Parse DINT (32-bit signed integer)
def parse_dint(data: bytes, offset: int) -> int:
    """Parse S7 DINT (Big Endian 4-byte signed int)"""
    return s7util.get_dint(data, offset)

# Parse BOOL
def parse_bool(data: bytes, byte_offset: int, bit_offset: int) -> bool:
    """Parse S7 BOOL at specific bit position"""
    return s7util.get_bool(data, byte_offset, bit_offset)
```

### 7.3 Batch Reading Strategy

```python
import snap7
from snap7.util import get_real, get_int

# [IMPORTANT] Read entire DB block at once, not individual addresses
# Reduces communication overhead, improves efficiency

class PLCService:
    def __init__(self, ip: str, rack: int = 0, slot: int = 1):
        self.client = snap7.client.Client()
        self.ip = ip
        self.rack = rack
        self.slot = slot

    def connect(self) -> bool:
        """Connect to PLC"""
        try:
            self.client.connect(self.ip, self.rack, self.slot)
            return self.client.get_connected()
        except Exception as e:
            raise ConnectionError(f"PLC connection failed: {e}")

    def read_kiln_data(self, db_number: int, start: int, size: int) -> bytes:
        """Read entire DB block at once"""
        return self.client.db_read(db_number, start, size)

    def disconnect(self):
        """Disconnect from PLC"""
        self.client.disconnect()
```

---

## 8. [IMPORTANT] InfluxDB Schema

### 8.1 Measurement Design

```
Measurements (表):
├── roller_kiln_temp      # 辊道窑温度数据
├── roller_kiln_energy    # 辊道窑能耗数据
├── rotary_kiln_temp      # 回转窑温度数据
├── rotary_kiln_energy    # 回转窑能耗数据
├── rotary_kiln_feed      # 回转窑下料数据
├── rotary_kiln_hopper    # 回转窑料仓数据
├── scr_fan               # SCR风机数据
├── scr_pump              # SCR氨水泵数据
├── scr_gas               # SCR燃气数据
└── alarms                # 报警记录

Tags (索引):
├── device_id             # 设备编号 (rotary_kiln: 1-3, scr: 1-2)
├── zone_id               # 温区编号
├── fan_id                # 风机编号
├── pump_id               # 水泵编号
├── pipeline_id           # 燃气管路编号 (1 或 2)
└── sensor_type           # 传感器类型

Fields (数值):
├── temperature           # 温度 °C
├── set_point             # 设定温度 °C
├── voltage               # 电压 V
├── current               # 电流 A
├── power                 # 功率 kW
├── total_energy          # 累计电量 kWh
├── feed_speed            # 下料速度 kg/h
├── hopper_weight         # 料仓重量 kg
├── hopper_percent        # 料仓百分比 %
├── flow_rate             # 燃气流速 m³/h
├── cumulative_volume     # 累计用量 m³
└── status                # 运行状态 (0/1)
```

### 8.2 详细 Measurement Schema

#### 8.2.1 辊道窑数据表

```flux
// roller_kiln_temp - 辊道窑温度数据
measurement: roller_kiln_temp
tags:
  - zone_id: string        # 温区ID "1", "2", ...
fields:
  - temperature: float     # 当前温度 °C
  - set_point: float       # 设定温度 °C

// roller_kiln_energy - 辊道窑能耗数据
measurement: roller_kiln_energy
tags: (none)
fields:
  - voltage: float         # 电压 V
  - current: float         # 电流 A
  - power: float           # 功率 kW
  - total_energy: float    # 累计电量 kWh
  - status: int            # 运行状态 0=停止, 1=运行
```

#### 8.2.2 回转窑数据表

```flux
// rotary_kiln_temp - 回转窑温度数据
measurement: rotary_kiln_temp
tags:
  - device_id: string      # 设备ID "1", "2", "3"
  - zone_id: string        # 温区ID "1" - "8"
fields:
  - temperature: float     # 当前温度 °C
  - set_point: float       # 设定温度 °C

// rotary_kiln_energy - 回转窑能耗数据
measurement: rotary_kiln_energy
tags:
  - device_id: string      # 设备ID "1", "2", "3"
fields:
  - voltage: float         # 电压 V
  - current: float         # 电流 A
  - power: float           # 功率 kW
  - total_energy: float    # 累计电量 kWh
  - status: int            # 运行状态 0=停止, 1=运行

// rotary_kiln_feed - 回转窑下料数据
measurement: rotary_kiln_feed
tags:
  - device_id: string      # 设备ID "1", "2", "3"
fields:
  - feed_speed: float      # 下料速度 kg/h

// rotary_kiln_hopper - 回转窑料仓数据
measurement: rotary_kiln_hopper
tags:
  - device_id: string      # 设备ID "1", "2", "3"
  - hopper_id: string      # 料仓ID
fields:
  - weight: float          # 当前重量 kg
  - capacity: float        # 总容量 kg
  - percent: float         # 容量百分比 %
  - low_alarm: int         # 低重量告警 0=正常, 1=告警
```

#### 8.2.3 SCR 设备数据表

```flux
// scr_fan - SCR风机数据
measurement: scr_fan
tags:
  - device_id: string      # SCR设备ID "1", "2"
  - fan_id: string         # 风机ID
fields:
  - power: float           # 功率 kW
  - cumulative_energy: float  # 累计电量 kWh
  - status: int            # 运行状态 0=停止, 1=运行

// scr_pump - SCR氨水泵数据
measurement: scr_pump
tags:
  - device_id: string      # SCR设备ID "1", "2"
  - pump_id: string        # 水泵ID
fields:
  - power: float           # 功率 kW
  - cumulative_energy: float  # 累计电量 kWh
  - status: int            # 运行状态 0=停止, 1=运行

// scr_gas - SCR燃气数据
measurement: scr_gas
tags:
  - device_id: string      # SCR设备ID "1", "2"
  - pipeline_id: string    # 管路ID "1", "2"
fields:
  - flow_rate: float       # 当前流速 m³/h
  - cumulative_volume: float  # 累计用量 m³
```

### 8.3 Retention Policy

```
数据保留策略:
├── realtime: 7天 (原始数据，5秒间隔)
├── hourly: 90天 (1小时聚合)
└── daily: 2年 (1天聚合)

# Continuous Query 自动聚合示例
# 每小时聚合回转窑温度数据
CREATE CONTINUOUS QUERY "cq_rotary_temp_hourly" ON "sensor_data"
BEGIN
  SELECT mean("temperature") AS "temperature"
  INTO "sensor_data"."hourly"."rotary_kiln_temp"
  FROM "sensor_data"."realtime"."rotary_kiln_temp"
  GROUP BY time(1h), device_id, zone_id
END
```

### 8.4 Write Strategy

```python
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import ASYNCHRONOUS
import asyncio
from typing import List

# [IMPORTANT] Buffered batch write, flush every 5 seconds
class InfluxWriter:
    def __init__(self, client: InfluxDBClient, bucket: str, org: str):
        self.write_api = client.write_api(write_options=ASYNCHRONOUS)
        self.bucket = bucket
        self.org = org
        self.buffer: List[Point] = []
        self.batch_size = 100
        self.flush_interval = 5  # seconds

    def add_point(self, point: Point):
        """Add point to buffer"""
        self.buffer.append(point)
        if len(self.buffer) >= self.batch_size:
            self.flush()

    def flush(self):
        """Write buffered points to InfluxDB"""
        if self.buffer:
            self.write_api.write(bucket=self.bucket, org=self.org, record=self.buffer)
            self.buffer.clear()
```

---

## 9. YAML Configuration Files (配置文件)

### 9.1 设备配置 (devices.yaml)

```yaml
# 回转窑设备 (7套)
rotary_kilns:
  - id: 1
    name: '回转窑1号'
    db_number: 10
    zone_count: 8
    hopper_capacity: 1000
    hopper_alarm_threshold: 200
    enabled: true
  # ... (2-7号设备)

# 辊道窑设备 (3-4套)
roller_kilns:
  - id: 1
    name: '辊道窑1号'
    db_number: 100
    zone_count: 12
    enabled: true
  # ... (2-4号设备)

# SCR设备 (2套)
scr_equipment:
  - id: 1
    name: 'SCR设备1号'
    db_number: 200
    fan_count: 4
    pump_count: 2
    enabled: true
  # ... (2号设备)
```

### 9.2 传感器地址映射 (sensors.yaml)

```yaml
# 回转窑传感器地址映射模板
rotary_kiln_template:
  temperature_zones:
    - zone_id: 1
      db_offset: 0
      data_type: 'WORD'
      scale: 0.1
      unit: '°C'
    # ... (8个温区)

  energy:
    voltage:
      db_offset: 20
      data_type: 'WORD'
      scale: 0.1
      unit: 'V'
    # ... (电流、功率等)

  feed_system:
    feed_speed:
      db_offset: 30
      data_type: 'WORD'
      unit: 'kg/h'
```

### 9.3 配置文件加载

```python
import yaml
from pathlib import Path

def load_config(config_file: str) -> dict:
    """加载 YAML 配置文件"""
    config_path = Path(config_file)
    with config_path.open('r', encoding='utf-8') as f:
        return yaml.safe_load(f)

# 使用示例
devices = load_config("configs/devices.yaml")
sensors = load_config("configs/sensors.yaml")

# 获取回转窑配置
rotary_kilns = devices['rotary_kilns']
for kiln in rotary_kilns:
    if kiln['enabled']:
        print(f"设备: {kiln['name']}, DB{kiln['db_number']}")
```

---

## 10. Dependency Injection Pattern

### 10.1 Service Interface Definition

```python
# services/interfaces.py
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from datetime import datetime

class IPLCService(ABC):
    """PLC Service Interface
    Methods:
    1. connect - Connect to PLC
    2. disconnect - Disconnect from PLC
    3. read_kiln_data - Read kiln data
    4. read_scr_data - Read SCR data
    """

    @abstractmethod
    def connect(self) -> bool:
        """Connect to PLC"""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from PLC"""
        pass

    @abstractmethod
    def read_kiln_data(self, device_id: int) -> Dict[str, Any]:
        """Read kiln data"""
        pass

    @abstractmethod
    def read_scr_data(self, device_id: int) -> Dict[str, Any]:
        """Read SCR data"""
        pass


class IInfluxService(ABC):
    """InfluxDB Service Interface
    Methods:
    1. write - Write time-series data
    2. query - Query historical data
    """

    @abstractmethod
    def write(self, measurement: str, tags: Dict[str, str],
              fields: Dict[str, Any]) -> None:
        """Write time-series data"""
        pass

    @abstractmethod
    def query(self, query: str) -> List[Dict[str, Any]]:
        """Query historical data"""
        pass
```

### 10.2 FastAPI Dependency Injection

```python
# dependencies.py
from functools import lru_cache
from app.services.plc_service import PLCService
from app.services.influx_service import InfluxService
from app.services.kiln_service import KilnService
from config import get_settings

@lru_cache()
def get_plc_service() -> PLCService:
    """Get singleton PLC service"""
    settings = get_settings()
    return PLCService(
        ip=settings.plc_ip,
        rack=settings.plc_rack,
        slot=settings.plc_slot
    )

@lru_cache()
def get_influx_service() -> InfluxService:
    """Get singleton InfluxDB service"""
    settings = get_settings()
    return InfluxService(
        url=settings.influx_url,
        token=settings.influx_token,
        org=settings.influx_org,
        bucket=settings.influx_bucket
    )

def get_kiln_service(
    plc: PLCService = Depends(get_plc_service),
    influx: InfluxService = Depends(get_influx_service)
) -> KilnService:
    """Get kiln service with injected dependencies"""
    return KilnService(plc, influx)
```

---

## 11. Development Commands

```powershell
# 启动开发环境
docker-compose up -d          # 启动 InfluxDB

# 运行后端服务
uvicorn main:app --reload --host 0.0.0.0 --port 8080  # 开发模式
python main.py                # 或直接运行

# 安装依赖
pip install -r requirements.txt

# 测试
pytest                        # 运行所有测试
pytest tests/ -v              # 详细输出
pytest --cov=app              # 测试覆盖率

# 代码检查
ruff check .                  # Linting
ruff format .                 # Formatting
mypy app/                     # Type checking
```

---

## 12. Docker Compose Configuration

```yaml
# docker-compose.yml
version: '3.8'
services:
  influxdb:
    image: influxdb:2.7
    container_name: ceramic-influxdb
    ports:
      - '8086:8086'
    volumes:
      - influxdb_data:/var/lib/influxdb2
    environment:
      - DOCKER_INFLUXDB_INIT_MODE=setup
      - DOCKER_INFLUXDB_INIT_USERNAME=admin
      - DOCKER_INFLUXDB_INIT_PASSWORD=ceramic123
      - DOCKER_INFLUXDB_INIT_ORG=ceramic-workshop
      - DOCKER_INFLUXDB_INIT_BUCKET=sensor_data
      - DOCKER_INFLUXDB_INIT_ADMIN_TOKEN=ceramic-workshop-token
    deploy:
      resources:
        limits:
          memory: 1G

volumes:
  influxdb_data:
```

---

## 13. Configuration File

```yaml
# configs/config.yaml (可选，也可以直接用环境变量)
server:
  port: 8080
  mode: debug # debug / release

plc:
  ip: 192.168.50.223
  rack: 0
  slot: 1
  timeout: 5s
  poll_interval: 5s

influxdb:
  url: http://localhost:8086
  token: ceramic-workshop-token
  org: ceramic-workshop
  bucket: sensor_data
```

---

## 14. Error Handling & Response Format

### 14.1 Standard Response

```python
from fastapi import HTTPException
from fastapi.responses import JSONResponse

# 成功响应
def success_response(data):
    return JSONResponse(content={
        "success": True,
        "data": data
    })

# 错误响应
def error_response(status_code: int, message: str):
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error": message
        }
    )

# 分页响应
def paginated_response(items, page: int, page_size: int, total: int):
    return JSONResponse(content={
        "success": True,
        "data": items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total
        }
    })
```

### 14.2 Error Codes

| Code | Description        |
| ---- | ------------------ |
| 400  | Bad Request        |
| 404  | Resource Not Found |
| 500  | Internal Error     |
| 503  | PLC Disconnected   |

---

## 15. Code Style Guidelines

### 15.1 Comment Convention

```python
class IKilnService(ABC):
    """KilnService Interface
    Methods:
    1. get_realtime_data - Get real-time data
    2. get_history_data - Get historical data
    3. start_polling - Start polling
    """

    @abstractmethod
    def get_realtime_data(self, device_id: int) -> KilnData:
        """Get real-time data"""
        pass

    @abstractmethod
    def get_history_data(self, device_id: int, start: datetime, end: datetime) -> List[KilnData]:
        """Get historical data"""
        pass

    @abstractmethod
    def start_polling(self) -> None:
        """Start polling"""
        pass
```

### 15.2 File Naming

| Type              | Pattern               | Example                  |
| ----------------- | --------------------- | ------------------------ |
| Model             | `{domain}.py`         | `kiln.py`                |
| Service Interface | `interfaces.py`       | `services/interfaces.py` |
| Service Impl      | `{domain}_service.py` | `kiln_service.py`        |
| Router            | `{domain}.py`         | `routers/kiln.py`        |

---

## 16. Testing Guidelines

```python
# 测试文件命名: test_{file}.py
# 测试函数命名: test_{function_name}

import pytest
from unittest.mock import Mock, patch
from app.services.kiln_service import KilnService

def test_kiln_service_get_realtime_data():
    # Arrange
    mock_plc = Mock()
    mock_influx = Mock()
    service = KilnService(mock_plc, mock_influx)

    # Act
    data = service.get_realtime_data(1)

    # Assert
    assert data is not None


@pytest.fixture
def kiln_service():
    """Fixture for KilnService with mocked dependencies"""
    mock_plc = Mock()
    mock_influx = Mock()
    return KilnService(mock_plc, mock_influx)
```

---

## 17. Troubleshooting

| Issue           | Solution                       |
| --------------- | ------------------------------ |
| PLC 连接失败    | 检查 IP、Rack=0、Slot=1        |
| 数据解析错误    | 确保使用 Big Endian 字节序     |
| InfluxDB 写入慢 | 启用批量写入，调整 batchSize   |
| 内存占用高      | 检查 InfluxDB retention policy |
| 跨域请求失败    | 检查 CORS 中间件配置           |

---

## 18. Security Considerations

- **[IMPORTANT]** 生产环境关闭 debug 模式
- **[IMPORTANT]** 配置文件不要提交敏感信息（使用环境变量）
- 局域网部署，无需公网暴露
- API 可选添加简单认证（Bearer Token）
