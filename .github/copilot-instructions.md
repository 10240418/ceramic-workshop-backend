---
alwaysApply: true
---

# Ceramic Workshop Backend - 开发规范

> **磨料车间后端 API** - FastAPI + WebSocket + InfluxDB + S7-1200 PLC

---

## 1. 项目概览

```yaml
项目名称: ceramic-workshop-backend
应用类型: 工业物联网后端 API
技术栈: Python 3.12 / FastAPI 0.109 / python-snap7 1.3 / WebSocket
数据库: InfluxDB 2.x (时序数据) + SQLite (本地缓存) + YAML (配置)
通信协议: Siemens S7-1200 PLC (S7 Protocol)
部署方式: Docker Compose (工控机本地部署)
前端: Flutter Desktop (Windows)
核心理念: WebSocket 实时推送 + 本地 InfluxDB 部署 + 高可靠性轮询
```

### 核心特性
- [完成] **WebSocket 实时推送**: 0.1s 间隔推送实时数据到前端
- [完成] **PLC 数据采集**: 每.env中配置秒从 PLC 读取数据
- [完成] **批量写入优化**: 10 次轮询后批量写入 InfluxDB（减少 90% 写入次数）
- [完成] **内存缓存**: 全局变量缓存最新数据，供 WebSocket 推送使用
- [完成] **本地缓存**: SQLite 缓存最新数据，提升 API 响应速度
- [完成] **自动投料分析**: 每 .env中配置小时自动分析投料事件
- [完成] **健康检查**: PLC 连接状态监控
- [完成] **动态配置**: 支持运行时修改 PLC 配置
- [完成] **HTTP 降级**: HTTP API 仅用于历史数据查询和配置管理

---

## 2. 设备清单

| DB块 | 设备 | 数量 | 模块 | 关键数据 |
|------|------|------|------|---------|
| **DB8** | 料仓 | 9个 | 电表+温度+称重 | `weight`, `feed_rate`, `temperature`, `Pt`, `ImpEp` |
| **DB9** | 辊道窑 | 1个(6温区) | 电表+温度 | `temperature`, `Pt`, `ImpEp`, `I_0~I_2` |
| **DB10** | SCR+风机 | 4个(2+2) | 电表+燃气 | `Pt`, `ImpEp`, `flow_rate`, `total_flow` |
| **DB3** | 料仓状态位 | 9个 | 数字量 | `error`, `status_code` |
| **DB7** | 辊道窑状态位 | 6个 | 数字量 | `error`, `status_code` |
| **DB11** | SCR/风机状态位 | 4个 | 数字量 | `error`, `status_code` |

### 设备详细映射

#### 料仓 (9个)
```yaml
short_hopper_1~4: 短料仓 (对应窑 7,6,5,4)
no_hopper_1~2:    无料仓 (对应窑 2,1)
long_hopper_1~3:  长料仓 (对应窑 8,3,9)
```

#### 辊道窑 (6温区)
```yaml
zone1~zone6: 1-6号温区
```

#### SCR + 风机 (4个)
```yaml
scr_1~2:  SCR氨水泵 (表63, 表64)
fan_1~2:  风机 (表65, 表66)
```

---

## 3. 架构设计

### 目录结构
```
ceramic-workshop-backend/
├── main.py                    # [入口] FastAPI 应用入口 (Lifespan 管理)
├── config.py                  # [配置] 配置管理 (pydantic-settings)
├── requirements.txt           # [依赖] Python 依赖
├── build_exe.bat              # [打包] PyInstaller 打包脚本
├── build_exe.spec             # [打包] PyInstaller 配置文件
├── README.md                  # [文档] 项目文档
│
├── configs/                   # [配置] YAML 配置文件
│   ├── plc_modules.yaml       # PLC 模块定义
│   ├── db_mappings.yaml       # DB 块映射
│   ├── config_hopper_8.yaml   # DB8 料仓配置
│   ├── config_roller_kiln_9.yaml  # DB9 辊道窑配置
│   ├── config_scr_fan_10.yaml     # DB10 SCR/风机配置
│   ├── status_hopper_3.yaml       # DB3 料仓状态位
│   ├── status_roller_kiln_7.yaml  # DB7 辊道窑状态位
│   └── status_scr_fan_11.yaml     # DB11 SCR/风机状态位
│
├── app/
│   ├── models/                # [模型] Pydantic 数据模型
│   │   ├── response.py        # 统一响应格式
│   │   ├── kiln.py            # 料仓/辊道窑模型
│   │   ├── scr.py             # SCR/风机模型
│   │   └── ws_messages.py     # [核心] WebSocket 消息模型
│   │
│   ├── services/              # [服务] 业务逻辑层
│   │   ├── ws_manager.py              # [核心] WebSocket 连接管理器
│   │   ├── polling_service.py         # [核心] PLC 轮询服务
│   │   ├── plc_service.py             # PLC 通信服务
│   │   ├── history_query_service.py   # 历史数据查询
│   │   ├── feeding_analysis_service.py # 投料分析
│   │   ├── roller_kiln_aggregator.py  # 辊道窑数据聚合
│   │   ├── alarm_checker.py           # 报警检查服务
│   │   ├── daily_summary_service.py   # 日报表服务
│   │   ├── data_export_service.py     # 数据导出服务
│   │   ├── mock_service.py            # Mock 数据生成
│   │   └── data_seeder.py             # 模拟数据生成
│   │
│   ├── routers/               # [路由] API 路由 (Controllers)
│   │   ├── websocket.py       # [核心] WebSocket 路由
│   │   ├── health.py          # 健康检查
│   │   ├── hopper.py          # 料仓 API (HTTP 降级)
│   │   ├── roller.py          # 辊道窑 API (HTTP 降级)
│   │   ├── scr_fan.py         # SCR/风机 API (HTTP 降级)
│   │   ├── status.py          # 状态位 API
│   │   ├── devices.py         # 设备列表 API
│   │   ├── config.py          # 配置管理 API
│   │   ├── alarm.py           # 报警 API
│   │   ├── daily_summary.py   # 日报表 API
│   │   └── export.py          # 数据导出 API
│   │
│   ├── core/                  # [核心] 核心工具
│   │   ├── influxdb.py        # InfluxDB 客户端
│   │   ├── influx_schema.py   # InfluxDB Schema 定义
│   │   ├── influx_migration.py # Schema 自动迁移
│   │   ├── local_cache.py     # SQLite 本地缓存
│   │   ├── alarm_store.py     # 报警存储
│   │   ├── logging_setup.py   # 日志配置
│   │   └── unified_naming.py  # 统一命名规范
│   │
│   ├── plc/                   # [PLC] PLC 通信模块
│   │   ├── s7_client.py       # S7 协议客户端
│   │   ├── snap7_compat.py    # Snap7 兼容层
│   │   ├── plc_manager.py     # PLC 连接管理
│   │   ├── config_manager.py  # 配置管理器
│   │   ├── config_storage.py  # 配置存储
│   │   ├── module_parser.py   # 模块解析器
│   │   ├── parser_hopper.py   # 料仓数据解析
│   │   ├── parser_roller_kiln.py # 辊道窑数据解析
│   │   ├── parser_scr_fan.py     # SCR/风机数据解析
│   │   └── parser_device_status.py # 状态位数据解析
│   │
│   ├── tools/                 # [工具] 数据转换器
│   │   ├── converter_base.py  # 转换器基类
│   │   ├── converter_elec.py  # 电表数据转换
│   │   ├── converter_temp.py  # 温度数据转换
│   │   ├── converter_weight.py # 称重数据转换
│   │   ├── converter_flow.py  # 流量数据转换
│   │   ├── time_slice_tools.py # 时间切片工具
│   │   └── timezone_tools.py  # 时区工具
│   │
│   └── alarm_thresholds.py    # [配置] 报警阈值配置
│
├── data/                      # [数据] 本地数据
│   ├── cache.db               # SQLite 缓存数据库
│   ├── influxdb_config/       # InfluxDB 配置目录
│   └── influxdb_data/         # InfluxDB 数据目录
│
├── logs/                      # [日志] 日志文件
│   ├── app.error.log          # 错误日志
│   └── server.log             # 服务器日志
│
├── scripts/                   # [脚本] 测试脚本
│   ├── tray_app.py            # 系统托盘应用
│   ├── fix_emoji.py           # Emoji 清理脚本
│   └── archive/               # 归档脚本
│
├── tests/                     # [测试] 单元测试
│   ├── integration/           # 集成测试
│   ├── mock/                  # Mock 数据
│   └── data_table/            # 数据表测试
│
├── vdoc/                      # [文档] 项目文档
│
├── deploy/                    # [部署] 部署版本
│   ├── 1.1.24/                # 最新版本
│   └── xlsx/                  # Excel 模板
│
├── dist/                      # [打包] 打包输出
│   └── WorkshopBackend/       # 可执行文件
│
├── python_packages/           # [依赖] Windows 离线包
└── python_packages_linux/     # [依赖] Linux 离线包
```

### 数据流架构 (WebSocket 优先)
```
┌─────────────┐
│ PLC S7-1200 │ (DB8/9/10/3/7/11)
└──────┬──────┘
       │ S7 Protocol (每 6 秒)
       ↓
┌──────────────────┐
│ polling_service  │ 轮询服务
└──────┬───────────┘
       │
       ↓
┌──────────────────┐
│ parser_*.py      │ 数据解析
└──────┬───────────┘
       │
       ↓
┌──────────────────┐
│ converter_*.py   │ 数据转换 (电流变比、单位转换)
└──────┬───────────┘
       │
       ├─────────────────────┬─────────────────────┐
       ↓                     ↓                     ↓
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│ Memory Cache │      │ local_cache  │      │  InfluxDB    │
│ (全局变量)    │      │  (SQLite)    │      │  (时序数据)   │
└──────┬───────┘      └──────────────┘      └──────────────┘
       │
       ↓ (0.1s 推送)
┌──────────────────┐
│  ws_manager.py   │ WebSocket 推送
└──────┬───────────┘
       │ WebSocket
       ↓
┌──────────────┐
│ Flutter App  │ 前端应用 (实时监控)
└──────────────┘

       ↑ HTTP (历史查询)
       │
┌──────────────┐
│  routers/    │ REST API (降级)
└──────────────┘
```

### 核心依赖
```python
# 框架
fastapi==0.109.0          # Web 框架
uvicorn==0.27.0           # ASGI 服务器
websockets==12.0          # ★ WebSocket 支持
pydantic==2.5.3           # 数据验证
pydantic-settings==2.1.0  # 配置管理

# 数据库
influxdb-client==1.40.0   # InfluxDB 客户端

# PLC 通信
python-snap7==1.3         # S7 协议

# 工具
python-dotenv==1.0.0      # 环境变量
pyyaml==6.0.1             # YAML 解析

# 安全
python-jose==3.3.0        # JWT
passlib==1.7.4            # 密码加密

# 测试
pytest==7.4.4             # 单元测试
httpx==0.26.0             # HTTP 客户端
```

---

## 3.1 核心组件说明

### WebSocket 层

**文件**: `app/services/ws_manager.py`, `app/routers/websocket.py`

- **ConnectionManager**: 单例模式，管理所有 WebSocket 连接
- **订阅频道**: `realtime` (实时数据), `device_status` (设备状态)
- **心跳机制**: 客户端 15s 发送，服务端 45s 超时断开
- **推送任务**: `asyncio.create_task()` 异步推送，避免阻塞
- **推送间隔**: 0.1s (100ms) 极快响应

**消息模型**: `app/models/ws_messages.py`
- 使用 Pydantic v2 进行消息验证
- 所有消息必须包含 `type` 字段
- 消息类型: `subscribe`, `unsubscribe`, `heartbeat`, `realtime_data`, `device_status`, `error`

### 轮询服务层

**文件**: `app/services/polling_service.py`

- **轮询间隔**: 6 秒
- **内存缓存**: 全局变量缓存最新数据，供 WebSocket 推送使用
- **三重写入**: 
  1. 更新内存缓存 (WebSocket 推送)
  2. 更新 SQLite 缓存 (HTTP 降级)
  3. 批量写入 InfluxDB (历史查询)
- **错误隔离**: 单个设备失败不影响整体轮询

### PLC 通信层

**文件**: `app/plc/plc_manager.py`, `app/plc/parser_*.py`

- **连接管理**: 自动重连机制
- **数据解析**: 基于 YAML 配置的偏移量解析
- **Mock 模式**: `MOCK_MODE=true` 时使用模拟数据

### 数据库层

**文件**: `app/core/influxdb.py`, `app/core/local_cache.py`

- **InfluxDB**: 时序数据存储，批量写入优化
- **SQLite**: 本地缓存，提升 HTTP API 响应速度
- **内存缓存**: 全局变量，供 WebSocket 推送使用

---

## 4. 代码规范

### [严格禁止] 在代码注释中使用 Emoji 表情符号

**原则**: 所有代码文件（包括 .py、.yaml、.md 等）的注释中，严格禁止使用任何 emoji 图标或表情符号。

**禁止的符号示例**:
```
禁止使用:           🏭 📋 🗂️ 🏗️ 🔌   🌐 🛠️ 🔨 💾 🧪 📦 🐳 📖 等任何 emoji
```

**正确的注释风格**:
```python
# [正确] 初始化 WebSocket 连接管理器
# [错误] 连接失败
# [注意] 这里需要使用线程安全的数据结构
# [警告] 不要在推送循环中执行阻塞操作
# [成功] 数据推送完成
```

**错误的注释风格（严格禁止）**:
```python
#  初始化连接管理器  // 禁止
#  错误：连接断开    // 禁止
#  注意事项          // 禁止
#  启动服务          // 禁止
```

**原因说明**:
1. **编码兼容性**: Emoji 可能在某些编辑器或终端中显示异常
2. **代码审查**: 纯文本注释更易于代码审查和搜索
3. **专业性**: 工业控制系统代码应保持严谨的专业风格
4. **版本控制**: Emoji 在 Git diff 中可能显示为乱码
5. **跨平台**: 不同操作系统对 Emoji 的支持程度不同
6. **可读性**: 纯文本注释在所有环境下都能正确显示

**替代方案**:
- 使用 `[正确]` 替代 ``
- 使用 `[错误]` 替代 ``
- 使用 `[注意]` 替代 ``
- 使用 `[警告]` 替代 ``
- 使用 `[成功]` 替代 ``
- 使用 `[禁止]` 替代 ``
- 使用 `[允许]` 替代 ``
- 使用 `[重要]` 替代 ``
- 使用 `[提示]` 替代 ``
- 使用 `[完成]` 替代 ``
- 使用 `[推荐]` 替代 ``
- 使用 `[不推荐]` 替代 ``

---

### 文件头注释 (必须)
```python
# ============================================================
# 文件说明: ws_manager.py - WebSocket 连接管理器
# ============================================================
# 方法列表:
# 1. connect()              - 处理客户端连接
# 2. disconnect()           - 处理客户端断开
# 3. broadcast()            - 广播消息到订阅者
# 4. start_push_loop()      - 启动推送循环
# ============================================================
```

### 方法注释 (必须)
```python
# ------------------------------------------------------------
# 1. connect() - 处理客户端连接
# ------------------------------------------------------------
async def connect(self, websocket: WebSocket):
    """
    处理新的 WebSocket 连接
    
    Args:
        websocket: WebSocket 连接对象
    """
    await websocket.accept()
    self.active_connections[websocket] = set()
    self.last_heartbeat[websocket] = datetime.now()
```

### WebSocket 代码规范

#### 1. 连接管理
```python
# [正确] 处理连接断开
try:
    await websocket.send_json(message)
except WebSocketDisconnect:
    manager.disconnect(websocket)
except RuntimeError as e:
    if "WebSocket is not connected" in str(e):
        manager.disconnect(websocket)
except Exception as e:
    logger.error(f"[WS] 发送失败: {e}", exc_info=True)
    manager.disconnect(websocket)

# [正确] 检查连接状态
if ws.application_state != WebSocketState.CONNECTED:
    manager.disconnect(ws)
    return

# [错误] 不处理异常
await websocket.send_json(message)  # 可能导致服务崩溃
```

#### 2. 异步任务规范
```python
# [正确] 使用 asyncio.create_task
self._push_task = asyncio.create_task(self._push_loop())

# [正确] 优雅停止任务
if self._push_task:
    self._push_task.cancel()
    try:
        await self._push_task
    except asyncio.CancelledError:
        pass

# [错误] 直接 await 会阻塞
await self._push_loop()  # 会阻塞主线程
```

#### 3. 内存缓存规范
```python
# [正确] 使用全局缓存
_latest_data: Dict[str, Any] = {}

def get_latest_data() -> Dict[str, Any]:
    return _latest_data.copy()

# [正确] 线程安全更新
def update_cache(device_id: str, data: dict):
    _latest_data[device_id] = data

# [错误] 每次查询数据库
data = query_influxdb()  # 性能差
```

#### 4. 日志规范
```python
# [正确] WebSocket 日志
logger.info(f"[WS] 新连接建立，当前连接数: {count}")
logger.debug(f"[WS] 推送 realtime_data -> {subs} 个订阅者")
logger.warning(f"[WS] 客户端心跳超时 ({delta:.0f}s)")

# [正确] 错误日志包含 traceback
logger.error(f"[WS] 推送任务异常: {e}", exc_info=True)

# [错误] 缺少上下文
logger.error("错误")  # 无法定位问题
```

### 编码原则

#### [要做]
- **代码自文档化**: 使用清晰的变量名和函数名
- **单一职责**: 每个函数只做一件事
- **类型注解**: 所有函数参数和返回值都要有类型注解
- **错误处理**: 使用 try-except 捕获异常，记录日志
- **日志记录**: 关键操作都要记录日志

#### [不要]
- **过度封装**: 不要为了封装而封装
- **提前优化**: 先实现功能，再优化性能
- **未使用的代码**: 及时删除注释掉的代码
- **魔法数字**: 使用常量替代硬编码的数字
---

## 5. API 设计规范

### WebSocket 接口 (主要)

**端点**: `ws://localhost:8080/ws/realtime`

**客户端消息**:
```json
{"type": "subscribe", "channel": "realtime"}
{"type": "subscribe", "channel": "device_status"}
{"type": "heartbeat", "timestamp": "2026-02-24T10:30:00Z"}
```

**服务端推送** (.env文件中的
PLC_POLL_INTERVAL=5
REALTIME_POLL_INTERVAL=5
STATUS_POLL_INTERVAL=5s 
决定间隔):
```json
{
  "type": "realtime_data",
  "success": true,
  "timestamp": "2026-02-24T10:30:00.000Z",
  "source": "plc",
  "data": {
    "hoppers": [
      {"device_id": "short_hopper_1", "temperature": 850.5, "weight": 450.2, ...}
    ],
    "roller_kiln": {
      "zones": [
        {"zone_id": "zone1", "temperature": 1200.5, "power": 85.6, ...}
      ]
    },
    "scr_fan": [
      {"device_id": "scr_1", "power": 25.3, "flow_rate": 15.8, ...}
    ]
  }
}

{
  "type": "device_status",
  "success": true,
  "timestamp": "2026-02-24T10:30:00.000Z",
  "source": "plc",
  "data": {
    "hoppers": [...],
    "roller_kiln": [...],
    "scr_fan": [...]
  },
  "summary": {"total": 14, "normal": 14, "error": 0}
}
```

### HTTP 接口 (降级)

**核心批量接口** (仅用于降级，不推荐频繁调用):

```http
GET /api/hopper/realtime/batch          # 9个料仓实时数据
GET /api/roller/realtime/formatted      # 辊道窑6温区实时数据
GET /api/scr-fan/realtime/batch         # 4个SCR+风机实时数据
GET /api/status/all                     # 所有设备状态位
```



### 系统接口

```http
# 健康检查
GET  /api/health                               # 系统健康状态
GET  /api/health/plc                           # PLC 连接状态
GET  /api/health/influxdb                      # InfluxDB 连接状态

# WebSocket 监控
GET  /api/ws/status                            # WebSocket 连接统计
GET  /api/ws/connections                       # 当前连接列表

# 配置管理
GET  /api/config/plc                           # 获取 PLC 配置
PUT  /api/config/plc                           # 更新 PLC 配置
POST /api/config/plc/test                      # 测试 PLC 连接

# 设备列表
GET  /api/devices/hoppers                      # 料仓列表
GET  /api/devices/zones                        # 温区列表
GET  /api/devices/scr                          # SCR列表
GET  /api/devices/fans                         # 风机列表
```

### 响应格式

#### 成功响应
```json
{
  "success": true,
  "data": {
    "device_id": "short_hopper_1",
    "temperature": 850.5,
    "weight": 450.2,
    "power": 12.5
  }
}
```

#### 失败响应
```json
{
  "success": false,
  "error": "设备 short_hopper_999 不存在"
}
```

#### 批量响应
```json
{
  "success": true,
  "data": {
    "devices": [
      {"device_id": "short_hopper_1", ...},
      {"device_id": "short_hopper_2", ...}
    ],
    "timestamp": "2026-01-26T12:00:00Z"
  }
}
```

#### 历史数据响应
```json
{
  "success": true,
  "data": [
    {
      "time": "2026-01-26T12:00:00Z",
      "temperature": 850.5,
      "weight": 450.2
    }
  ],
  "count": 100
}
```

### 查询参数

#### 时间范围
```http
?start=2026-01-26T00:00:00Z    # 开始时间 (ISO 8601)
?end=2026-01-26T23:59:59Z      # 结束时间 (ISO 8601)
```

#### 聚合
```http
?interval=1h                    # 聚合间隔 (1m, 5m, 1h, 1d)
?aggregate=mean                 # 聚合函数 (mean, max, min, sum)
```


---

## 6. PLC 通信规范

### S7-1200 连接配置
```yaml
IP: 192.168.50.223(由.env文件配置)
Rack: 0              # S7-1200 固定值
Slot: 1              # S7-1200 固定值
Timeout: 5000ms      # 连接超时
Poll_Interval: 6s    # 轮询间隔
```

### 数据类型 (Big Endian 字节序)

```python
import snap7.util as s7util

# REAL (32-bit float, 4 bytes)
temperature = s7util.get_real(data, offset=0)

# INT (16-bit signed, 2 bytes)
status_code = s7util.get_int(data, offset=4)

# DINT (32-bit signed, 4 bytes)
total_count = s7util.get_dint(data, offset=6)

# BOOL (1 bit)
error_flag = s7util.get_bool(data, byte_offset=10, bit_offset=0)

# WORD (16-bit unsigned, 2 bytes)
status_word = s7util.get_word(data, offset=12)
```



### 错误处理

```python
from snap7.exceptions import Snap7Exception

try:
    data = client.db_read(db_number, start, size)
except Snap7Exception as e:
    if "Address out of range" in str(e):
        logger.error(f"DB{db_number} 地址越界，检查 size 参数")
    elif "Connection" in str(e):
        logger.error(f"PLC 连接失败，检查 IP: {plc_ip}")
    else:
        logger.error(f"PLC 读取失败: {e}")
    raise
```

### 电流变比说明

**重要**: 电表读取的是电流互感器二次侧数据，需要乘以变比得到一次侧实际电流。

| 设备类型 | 电流变比 | 计算公式 | 示例 |
|---------|---------|---------|------|
| **辊道窑** (DB9) | 60 | `实际电流 = PLC值 × 0.1 × 60` | PLC=50 → 300A |
| **料仓** (DB8) | 20 | `实际电流 = PLC值 × 0.1 × 20` | PLC=50 → 100A |
| **SCR/风机** (DB10) | 20 | `实际电流 = PLC值 × 0.1 × 20` | PLC=50 → 100A |

**代码实现**:
```python
# converter_elec.py
def convert_current(plc_value: float, device_type: str) -> float:
    """转换电流值（应用变比）"""
    ratio = 60 if device_type == "roller_kiln" else 20
    return plc_value * 0.1 * ratio
```

---

## 7. InfluxDB 规范

### Measurement 设计

```python
# 料仓数据
measurement: "hopper_data"
tags: {
    "device_id": "short_hopper_1",
    "device_type": "short_hopper"
}
fields: {
    "temperature": 850.5,      # 温度 (°C)
    "weight": 450.2,           # 重量 (kg)
    "feed_rate": 12.5,         # 投料速率 (kg/h)
    "Pt": 15.8,                # 有功功率 (kW)
    "ImpEp": 1250.3            # 累计电量 (kWh)
}

# 辊道窑数据
measurement: "roller_kiln_data"
tags: {
    "zone_id": "zone1",
    "device_type": "roller_kiln"
}
fields: {
    "temperature": 1200.5,     # 温度 (°C)
    "Pt": 85.6,                # 有功功率 (kW)
    "ImpEp": 5420.8,           # 累计电量 (kWh)
    "Ua_0": 380.5,             # A相电压 (V)
    "I_0": 120.3,              # A相电流 (A)
    "I_1": 118.7,              # B相电流 (A)
    "I_2": 122.1               # C相电流 (A)
}

# SCR/风机数据
measurement: "scr_fan_data"
tags: {
    "device_id": "scr_1",
    "device_type": "scr"
}
fields: {
    "Pt": 25.3,                # 有功功率 (kW)
    "ImpEp": 850.6,            # 累计电量 (kWh)
    "flow_rate": 15.8,         # 流量 (m³/h)
    "total_flow": 12500.3      # 累计流量 (m³)
}

# 状态位数据
measurement: "device_status"
tags: {
    "device_id": "short_hopper_1",
    "device_type": "hopper"
}
fields: {
    "error": false,            # 故障标志
    "status_code": 0           # 状态码
}
```




### 测试

```bash
# 运行所有测试
pytest tests/ -v

# 运行集成测试
pytest tests/integration/ -v

# 运行单个测试文件
pytest tests/integration/test_db8_full_flow.py -v

# 测试 API
python scripts/test_all_apis.py

# 测试完整数据流
python scripts/test_complete_flow.py

---

## 9. 环境变量

### .env 文件配置

```bash
# ============================================================
# 磨料车间后端配置文件示例
# ============================================================
# 使用说明:
# 1. 复制此文件为 .env
# 2. 按实际现场修改参数
# 3. 重启 exe 或后端进程使配置生效
# ============================================================

# ============================================================
# 1. 服务器配置
# ============================================================
SERVER_HOST=0.0.0.0
SERVER_PORT=8080
DEBUG=false

# ============================================================
# 2. 运行模式配置
# ============================================================
# true=Mock模式（不依赖真实 PLC）
MOCK_MODE=true

# true=启用轮询服务
ENABLE_POLLING=true

# true=输出详细轮询日志
VERBOSE_POLLING_LOG=true

# 轮询间隔（秒）
PLC_POLL_INTERVAL=5
REALTIME_POLL_INTERVAL=5
STATUS_POLL_INTERVAL=5

# Mock 扩展配置
# 固定随机种子（留空表示每次随机）
MOCK_RANDOM_SEED=
# 状态位错误率（0.0 - 1.0）
MOCK_ERROR_RATE=0.03

# 预留档位：realistic/aggressive/stable
MOCK_DATA_PROFILE=realistic

# ============================================================
# 3. PLC 配置（生产模式）
# ============================================================
PLC_IP=192.168.50.223
PLC_RACK=0
PLC_SLOT=1
PLC_TIMEOUT=5000

# ============================================================
# 4. InfluxDB 配置
# ============================================================
INFLUX_ORG=clutchtech
INFLUX_URL=http://localhost:8086
INFLUX_TOKEN=hMzMtpYmkARYOMoiS9kSidElkKz_FNHPuGQeKXXDruP8R7_HVOE25h7M-Gkz7yaG9K0W_cgZXIviyz2XAkq8Mw==
INFLUX_BUCKET=sensor_data

# ============================================================
# 5. 批量写入与本地缓存
# ============================================================
BATCH_WRITE_SIZE=10
LOCAL_CACHE_PATH=data/cache.db

# ============================================================
# 6. 投料分析算法参数
# ============================================================
# 滑动窗口大小 (单位: 次轮询次数, 建议 12~360)
# 窗口越大, 下料速度平滑性越好, 但实时性越低
FEEDING_WINDOW_SIZE=36
# 每隔多少次轮询触发一次速度和投料总量计算 (建议 <= FEEDING_WINDOW_SIZE/3)
FEEDING_CALC_INTERVAL=12

# ============================================================
# 6. 日志配置（error 文件日志 + 60 天保留）
# ============================================================
LOG_DIR=logs
LOG_FILE_NAME=app.error.log
LOG_RETENTION_DAYS=60
LOG_LEVEL=INFO




```


### 生产环境配置

```bash
# 生产环境建议配置
DEBUG=false
VERBOSE_POLLING_LOG=false
ENABLE_POLLING=true
MOCK_MODE=false
BATCH_WRITE_SIZE=10
```

---

## 10. 常见问题与解决方案

### WebSocket 问题

| 问题 | 原因 | 解决方案 |
|-----|------|---------|
| `WebSocket 连接断开` | 心跳超时/网络中断 | 1. 检查客户端心跳间隔 (应 < 45s)<br>2. 实现客户端重连机制<br>3. 查看服务端日志 `[WS]` 标记 |
| `推送延迟高` | 推送间隔过大 | 1. 检查 `WS_PUSH_INTERVAL` 配置 (默认 0.1s)<br>2. 确保轮询服务正常运行<br>3. 优先使用内存缓存 |
| `内存持续增长` | 连接未清理 | 1. 检查 `disconnect()` 是否正确调用<br>2. 实现心跳超时清理机制<br>3. 限制缓存大小 |
| `多个客户端数据不同步` | 推送逻辑错误 | 1. 确保使用 `broadcast()` 广播<br>2. 检查订阅频道是否正确 |

### PLC 连接问题

| 问题 | 原因 | 解决方案 |
|-----|------|---------|
| `Connection failed` | 网络不通 | 1. `ping 192.168.50.223` 检查网络<br>2. 检查防火墙设置<br>3. 确认 PLC 在线 |
| `Address out of range` | DB块大小不足 | 1. 检查 YAML 配置中的 `size` 参数<br>2. 在 TIA Portal 中确认 DB 块实际大小 |
| `Invalid Rack/Slot` | 参数错误 | S7-1200 固定使用 `Rack=0, Slot=1` |
| `Timeout` | 响应超时 | 1. 增加 `PLC_TIMEOUT` 值<br>2. 检查 PLC 负载 |

### InfluxDB 问题

| 问题 | 原因 | 解决方案 |
|-----|------|---------|
| `Bucket not found` | Bucket 未创建 | 1. 访问 http://localhost:8086<br>2. 手动创建 `sensor_data` Bucket |
| `Unauthorized` | Token 错误 | 1. 检查 `.env` 中的 `INFLUX_TOKEN`<br>2. 在 InfluxDB UI 中重新生成 Token |
| `Write timeout` | 批量写入过大 | 减小 `BATCH_WRITE_SIZE` 值 |
| `Connection refused` | InfluxDB 未启动 | `docker-compose up -d` 启动 InfluxDB |

### 数据解析问题

| 问题 | 原因 | 解决方案 |
|-----|------|---------|
| 温度值异常 (如 -999) | 字节序错误 | 确保使用 Big Endian (`s7util.get_real`) |
| 电流值偏小 | 未应用变比 | 检查 `converter_elec.py` 中的变比计算 |
| 数据全为 0 | PLC 未写入数据 | 1. 检查 PLC 程序是否运行<br>2. 确认 DB 块地址映射 |

---

## 11. 最佳实践

### WebSocket 开发流程

1. **本地开发**
   ```bash
   # 1. 启动 InfluxDB
   docker-compose up -d
   
   # 2. 使用 Mock 模式开发
   export MOCK_MODE=true
   python main.py
   
   # 3. 测试 WebSocket
   # 使用 websocat 或前端应用测试
   ```

2. **集成测试**
   ```bash
   # 1. 连接真实 PLC
   export MOCK_MODE=false
   export PLC_IP=192.168.50.223
   
   # 2. 运行集成测试
   pytest tests/integration/ -v
   ```

3. **生产部署**
   ```bash
   # 1. 构建 Docker 镜像
   docker build -t ceramic-backend:1.0.0 .
   
   # 2. 部署到工控机
   docker run -d --name ceramic-backend \
     -p 8080:8080 \
     -e ENABLE_POLLING=true \
     -e MOCK_MODE=false \
     ceramic-backend:1.0.0
   ```

### 性能优化建议

1. **WebSocket 优先**: 前端使用 WebSocket 接收实时数据，HTTP 仅用于历史查询
2. **内存缓存**: 优先使用内存缓存，减少数据库查询
3. **合理轮询间隔**: 6 秒是平衡实时性和性能的最佳值
4. **批量写入**: 保持 `BATCH_WRITE_SIZE=10` (1分钟写入一次)
5. **异步推送**: 使用 `asyncio.gather()` 并发推送，避免阻塞
6. **日志控制**: 生产环境关闭详细日志

### WebSocket 安全建议

1. **心跳超时**: 设置合理的心跳超时时间（45秒）
2. **连接限制**: 限制单个客户端的最大连接数
3. **消息验证**: 使用 Pydantic 验证所有消息格式
4. **错误隔离**: 单个连接错误不影响其他连接
5. **资源清理**: 连接断开时及时清理资源

---

## 12. AI 编码指令

**AI 指令**:

1. **WebSocket 优先**: 实时数据推送必须使用 WebSocket，HTTP 接口仅作为降级方案。
2. **简单至上**: 能用简单逻辑实现的，不要引入复杂的类层次结构。
3. **防崩溃**: 防止崩溃和任何内存泄漏,稳定是绝对的第一优先级,任何涉及 I/O (网络, 数据库, WebSocket) 的操作必须遵守.
4. **清晰日志**: 报错时产生的日志必须包含 traceback 和上下文信息。
5. **配置优先**: 在修改代码时，优先检查 `configs/` 目录，通过配置驱动逻辑。
6. **分层架构**: 保持 "Router-Service-Core" 的分层结构，职责清晰。
7. **连接管理**: WebSocket 连接必须正确处理断开、超时和重连场景。
8. **性能优化**: 使用内存缓存减少数据库查询，批量写入减少网络开销。
9. **本地优先**: 推荐使用本地 InfluxDB 部署，避免 Docker 网络延迟。
10. **协议规范**: 严格遵循 `docs/WEBSOCKET_PROTOCOL.md` 中定义的消息格式和通信流程。

## 其他规范

- **PowerShell 命令**：不支持 `&&`，使用分号 `;` 分隔命令
- **称呼**：每次回答必须称呼我为"大王"
- **测试文件**：不要创建多余的 md/py/test 文件，测试完毕后一定要删除,并且我的任何测试代码不要使用 emoji.
- **文档管理**：md 文件需要放到 `vdoc/` 目录里面
- **代码整洁**：目录务必整洁，修改代码时删除旧代码，不要冗余
- **回答执行规范**：你是一个很严格的python pyqt6写上位机的高手,你很严谨认真,且对代码很严苛,不会写无用冗余代码,并且很多问题,对于我希望实现的效果和架构你会认真思考,如果我的提议不好或者你有更好的方案,你会规劝我.
- **反驳我的回答** 对于我说的需求等的话,肯定会有一些东西说的不专业,如果你理解了的话,就回答我,"大王,小的罪该万死,但是这个XXXX"这样回答.
- **编码问题** 我的代码文件肯定会就是有中文和python代码,以及可能会有图标,所以的话,生成的代码需要规避编码问题错误.
- **log以及代码文件** 我的代码文件以及log的输出的话,等一切不要使用图标等标注. .这样的.
- **不要虚构** 回答我以及生成的md文件之中一定要和我的实际的代码文件相关,而不是虚构的.
- **不使用虚拟环境启动python**
- **必须真实有效的回答我,不能虚构**不要虚构任何我项目没有的文件,回答也必须严谨有效,而不是虚构.


## 13. 技术支持

### 文档链接

- **FastAPI**: https://fastapi.tiangolo.com/
- **WebSocket**: https://websockets.readthedocs.io/
- **InfluxDB**: https://docs.influxdata.com/
- **python-snap7**: https://python-snap7.readthedocs.io/
- **Pydantic**: https://docs.pydantic.dev/

### 项目文档

- `docs/WEBSOCKET_PROTOCOL.md` - WebSocket 协议规范（与前端共享）
- `README.md` - 项目说明
- `API_README.md` - API 接口文档
- `configs/*.yaml` - 设备配置文件

---

