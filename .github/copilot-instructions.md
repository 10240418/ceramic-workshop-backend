# Ceramic Workshop Backend - AI Coding Instructions

> **Reading Priority for AI:**
>
> 1. **[CRITICAL]** - Hard constraints, must strictly follow
> 2. **[IMPORTANT]** - Key specifications
> 3. Other content - Reference information

---

## 1. Project Overview

| Property         | Value                                                           |
| ---------------- | --------------------------------------------------------------- |
| **Type**         | Industrial IoT Backend API Service                              |
| **Stack**        | Python 3.11+ / FastAPI / python-snap7 / SQLAlchemy              |
| **Architecture** | Layered: Models → Services → Routers (Controllers)              |
| **Database**     | InfluxDB (Time-series) + MySQL (Config/Metadata)                |
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
│  └──────────────┘      └──────┬───────┘      │  MySQL       │       │
│         ▲                     │              └──────────────┘       │
│         │                     │ S7 Protocol (python-snap7)          │
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
├── docker-compose.yml   # InfluxDB + MySQL + Backend deployment
└── Dockerfile           # Python container image
```

---

## 4. Equipment Data Model

### 4.1 Roller Kiln (辊道窑)

```python
from pydantic import BaseModel
from datetime import datetime
from typing import List

class ZoneTemp(BaseModel):
    zone_id: int
    temperature: float  # Temperature °C

class RollerKilnData(BaseModel):
    timestamp: datetime
    zones: List[ZoneTemp]    # Multi-zone temperatures
    voltage: float           # Voltage V
    current: float           # Current A
    power: float             # Power kW
```

### 4.2 Rotary Kiln (回转窑)

```python
from pydantic import BaseModel
from datetime import datetime
from typing import List

class RotaryKilnData(BaseModel):
    timestamp: datetime
    device_id: int           # Device ID 1-3
    zones: List[float]       # 8-zone temperatures
    voltage: float           # Voltage V
    current: float           # Current A
    power: float             # Power kW
    feed_speed: float        # Feed speed kg/h
    hopper_weight: float     # Hopper weight kg
    hopper_percent: float    # Hopper capacity %
```

### 4.3 SCR Equipment (SCR 设备)

```python
from pydantic import BaseModel
from datetime import datetime
from typing import List

class FanData(BaseModel):
    fan_id: int
    power: float             # Power kW
    cumulative_energy: float # Cumulative energy kWh
    status: bool             # Running status

class PumpData(BaseModel):
    pump_id: int
    power: float             # Power kW
    cumulative_energy: float # Cumulative energy kWh
    status: bool             # Running status

class SCRData(BaseModel):
    timestamp: datetime
    device_id: int           # Device ID 1-2
    fans: List[FanData]      # Fan data
    ammonia_pumps: List[PumpData]  # Ammonia pump data
    gas_flows: List[float]   # 2 gas pipeline flows
    status: bool             # Running status
```

---

## 5. [CRITICAL] API Endpoints Design

### 5.1 Real-time Data API

```http
GET /api/v1/kiln/roller/realtime      # 辊道窑实时数据
GET /api/v1/kiln/rotary/:id/realtime  # 回转窑实时数据 (id: 1-3)
GET /api/v1/scr/:id/realtime          # SCR实时数据 (id: 1-2)
GET /api/v1/health                    # 健康检查
```

### 5.2 Historical Data API

```http
GET /api/v1/kiln/roller/history?start=&end=&interval=
GET /api/v1/kiln/rotary/:id/history?start=&end=&interval=
GET /api/v1/scr/:id/history?start=&end=&interval=

# Query Parameters:
# - start: ISO8601 时间戳
# - end: ISO8601 时间戳
# - interval: 1m, 5m, 1h, 1d (降采样间隔)
```

### 5.3 Configuration API

```http
GET  /api/v1/config/plc           # 获取PLC配置
PUT  /api/v1/config/plc           # 更新PLC配置
POST /api/v1/config/plc/test      # 测试PLC连接
GET  /api/v1/config/sensors       # 获取传感器配置
PUT  /api/v1/config/sensors       # 更新传感器配置
```

---

## 6. [CRITICAL] PLC Communication

### 6.1 S7 Protocol Configuration

```yaml
PLC Config:
  IP: 192.168.0.1
  Rack: 0
  Slot: 1
  Timeout: 5s
# [CRITICAL] S7-1200 固定参数
# Rack = 0, Slot = 1
```

### 6.2 Data Types & Byte Order

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

### 6.3 Batch Reading Strategy

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

## 7. [IMPORTANT] InfluxDB Schema

### 7.1 Measurement Design

```
Measurements (表):
├── roller_kiln          # 辊道窑数据
├── rotary_kiln          # 回转窑数据
├── scr_equipment        # SCR设备数据
└── alarms               # 报警记录

Tags (索引):
├── device_id            # 设备编号
├── zone_id              # 温区编号
└── sensor_type          # 传感器类型

Fields (数值):
├── temperature          # 温度
├── voltage              # 电压
├── current              # 电流
├── power                # 功率
└── ...
```

### 7.2 Retention Policy

```
数据保留策略:
├── realtime: 7天 (原始数据，5秒间隔)
├── hourly: 90天 (1小时聚合)
└── daily: 2年 (1天聚合)
```

### 7.3 Write Strategy

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

## 8. Dependency Injection Pattern

### 8.1 Service Interface Definition

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

### 8.2 FastAPI Dependency Injection

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

## 9. Development Commands

```powershell
# 启动开发环境
docker-compose up -d          # 启动 InfluxDB + MySQL

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

## 10. Docker Compose Configuration

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

  mysql:
    image: mysql:8.0
    container_name: ceramic-mysql
    ports:
      - '3306:3306'
    volumes:
      - mysql_data:/var/lib/mysql
    environment:
      - MYSQL_ROOT_PASSWORD=ceramic123
      - MYSQL_DATABASE=ceramic_workshop

volumes:
  influxdb_data:
  mysql_data:
```

---

## 11. Configuration File

```yaml
# configs/config.yaml
server:
  port: 8080
  mode: debug # debug / release

plc:
  ip: 192.168.0.1
  rack: 0
  slot: 1
  timeout: 5s
  poll_interval: 5s

influxdb:
  url: http://localhost:8086
  token: ceramic-workshop-token
  org: ceramic-workshop
  bucket: sensor_data

mysql:
  host: localhost
  port: 3306
  user: root
  password: ceramic123
  database: ceramic_workshop
```

---

## 12. Error Handling & Response Format

### 12.1 Standard Response

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

### 12.2 Error Codes

| Code | Description        |
| ---- | ------------------ |
| 400  | Bad Request        |
| 404  | Resource Not Found |
| 500  | Internal Error     |
| 503  | PLC Disconnected   |

---

## 13. Code Style Guidelines

### 13.1 Comment Convention

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

### 13.2 File Naming

| Type              | Pattern               | Example                  |
| ----------------- | --------------------- | ------------------------ |
| Model             | `{domain}.py`         | `kiln.py`                |
| Service Interface | `interfaces.py`       | `services/interfaces.py` |
| Service Impl      | `{domain}_service.py` | `kiln_service.py`        |
| Router            | `{domain}.py`         | `routers/kiln.py`        |

---

## 14. Testing Guidelines

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

## 15. Troubleshooting

| Issue           | Solution                       |
| --------------- | ------------------------------ |
| PLC 连接失败    | 检查 IP、Rack=0、Slot=1        |
| 数据解析错误    | 确保使用 Big Endian 字节序     |
| InfluxDB 写入慢 | 启用批量写入，调整 batchSize   |
| 内存占用高      | 检查 InfluxDB retention policy |
| 跨域请求失败    | 检查 CORS 中间件配置           |

---

## 16. Security Considerations

- **[IMPORTANT]** 生产环境关闭 debug 模式
- **[IMPORTANT]** 配置文件不要提交敏感信息（使用环境变量）
- 局域网部署，无需公网暴露
- API 可选添加简单认证（Bearer Token）
