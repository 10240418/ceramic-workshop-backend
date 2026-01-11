# Ceramic Workshop Backend - AI Coding Guidelines

> **Project Identity**: `ceramic-workshop-backend` (FastAPI + InfluxDB + S7-1200)
> **Role**: AI Assistant for Industrial IoT Backend Development

## 1. 核心架构原则 (Core Principles)

1.  **数据与状态处理 (Data vs Status separation)**:
    - **Data (DB8/9/10)**: 传感器数值，通过轮询服务 (PollingService) 解析后存入 InfluxDB。
    - **Status (DB3/7/11)**: 设备通信状态，后端仅负责**透传**或**简单缓存**，主要由前端解析（目前后端读取原始字节并提供 `/api/status` 接口）。

2.  **配置驱动 (Configuration Driven)**:
    - **db_mappings.yaml**: 核心映射表，定义 DB 块号、大小及对应的配置文件。
    - **config_*.yaml**: 具体设备内存布局，引用 `plc_modules.yaml` 中的基础模块。
    - **原则**: 新增设备或调整偏移量时，优先修改 YAML 配置，尽量不修改代码。

3.  **高可靠性轮询 (High Reliability Polling)**:
    - **长连接**: `PLCManager` 单例维护 S7 连接，避免频繁握手。
    - **批量写入**: 采集数据缓存 20-30 次后批量写入 InfluxDB，减少 I/O 压力。
    - **本地降级**: InfluxDB 不可用时自动降级写入 SQLite (LocalCache)，恢复后自动回放。

## 2. 数据流架构 (Data Flow Architecture)

```mermaid
graph TD
    PLC[S7-1200 PLC] -->|S7 Protocol| PollingService
    
    subgraph PollingService
        direction TB
        Conn[PLC Manager (Singleton)]
        
        subgraph Parsing
            P_Hopper[HopperParser (DB8)]
            P_Roller[RollerKilnParser (DB9)]
            P_SCR[SCRFanParser (DB10)]
        end
        
        subgraph Logic
            Converter[Data Converter (Raw -> Physical)]
            Buffer[Batch Buffer]
            LocalCache[SQLite Cache (Fallback)]
        end
    end
    
    PLC -->|DB8/9/10| P_Hopper & P_Roller & P_SCR
    P_Hopper & P_Roller & P_SCR --> Converter
    Converter --> Buffer
    
    Buffer -->|Batch Write| InfluxDB[(InfluxDB)]
    Buffer -.->|Fail| LocalCache
    LocalCache -.->|Retry| InfluxDB
    
    InfluxDB -->|Query| API[FastAPI Endpoints]
```

## 3. 关键文件结构 (Project Structure)

```text
ceramic-workshop-backend/
├── main.py                           # FastAPI 入口 (Lifespan管理)
├── config.py                         # 全局配置 (Env加载)
├── configs/                          # [核心配置层]
│   ├── db_mappings.yaml              # ★ DB块映射总表 (Poll Config)
│   ├── plc_modules.yaml              # ★ 基础模块定义 (Modules)
│   ├── config_hoppers.yaml           # DB8 配置
│   ├── config_roller_kiln.yaml       # DB9 配置
│   └── config_scr_fans.yaml          # DB10 配置
├── app/
│   ├── core/
│   │   ├── influxdb.py               # InfluxDB 读写封装
│   │   ├── local_cache.py            # SQLite 本地降级缓存
│   │   └── influx_migration.py       # 自动Schema迁移
│   ├── plc/                          # [PLC 层]
│   │   ├── plc_manager.py            # 连接管理器 (Reconnect)
│   │   ├── parser_*.py               # 各模块解析器
│   │   └── s7_client.py              # Snap7 客户端封装
│   ├── tools/                        # [转换层]
│   │   ├── converter_elec.py         # 电表 (14->8字段精简)
│   │   ├── converter_weight.py       # 称重 (计算FeedRate)
│   │   └── ...
│   ├── services/                     # [服务层]
│   │   ├── polling_service.py        # 核心轮询逻辑
│   │   └── history_query_service.py  # 历史数据查询
│   └── routers/                      # [API 路由]
│       ├── hopper.py                 # 料仓接口
│       ├── roller.py                 # 辊道窑接口
│       └── status.py                 # 状态数据接口
└── docker-compose.yml                # 容器编排
```

## 4. 核心实现规范 (Implementation Specs)

### 4.1 数据解析与转换流程

1.  **Parse (解析)**: `Parser` 类读取 `config_*.yaml` 中的偏移量，将 PLC `bytes` 解析为 Python 字典 (Raw Values)。
    - *Tip*: Parser 不进行单位转换，只按 Byte/Word/Real 读取数值。
2.  **Convert (转换)**: `Converter` 类将 Raw Values 转换为物理量 (Physical Values)。
    - 例: `ElectrocityMeterConverter` 将 14 个原始电表字段精简为 `Pt`, `Ua`, `Ia` 等 8 个核心字段。
    - 例: `WeightConverter` 结合历史数据计算 `feed_rate` (下料速度)。

### 4.2 轮询服务特性 (`polling_service.py`)

- **Mock 模式**: 当 `MOCK_MODE=true` 或无法连接 PLC 时，自动切换到 Mock 数据生成，保障前端开发。
- **状态字节读取**: 专门读取 DB3/7/11 的原始字节，缓存到 `_latest_device_status_bytes`，供 `/api/status/raw/{db_type}` 接口调用。

### 4.3 InfluxDB 设计

- **Measurement**: `sensor_data` (单表存储)。
- **Tags**: `device_id`, `device_type`, `module_type`。
- **Fields**: `temperature`, `weight`, `feed_rate`, `Pt`, `Ua_0`... (动态字段)。

## 5. API 接口规范

- **Base URL**: `http://localhost:8080`
- **Endpoints**:
    - `GET /api/hopper/list`: 料仓列表 (含实时数据)。
    - `GET /api/roller/realtime`: 辊道窑实时数据 (含各区温度/电表)。
    - `GET /api/status/realtime`: 设备通信状态。
    - `GET /api/health`: 系统健康检查 (InfluxDB连接状态, 队列长度)。

## 6. 复用指南 (Replication Guide)

如果需要基于此架构创建新项目（如：`ceramic-new-factory-backend`）：

1.  **结构复制**: 完整复制 `app/` 和 `configs/` 目录。
2.  **配置适配**:
    - 修改 `configs/db_mappings.yaml` 中的 DB 块号和大小。
    - 根据新 PLC 的变量表，更新 `configs/config_*.yaml`。
    - 若有新设备类型，在 `configs/plc_modules.yaml` 定义新模块结构。
3.  **解析器调整**:
    - 若设备结构变化，在 `app/plc/` 下新增或修改 `Parser` 类。
    - 确保 `polling_service.py` 中注册了新的 `Parser`。
4.  **转换逻辑**: 若有特殊计算（如流量累积、速度计算），在 `app/tools/` 新增 Converter。
5.  **端口配置**: 修改 `docker-compose.yml` 和 `main.py` 中的端口，避免冲突。

---

**AI 指令**: 
1. 在修改代码时，优先检查 `configs/` 目录，通过配置驱动逻辑。
2. 涉及 PLC 通信时，注意 S7-1200 的大端序 (`Big Endian`) 特性。
3. 新增功能时，保持 "Controller-Service-Dao" (Router-Service-Core) 的分层结构。
