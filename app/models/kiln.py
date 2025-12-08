# ============================================================
# 文件说明: kiln.py - 窑炉数据模型 (辊道窑 + 回转窑)
# ============================================================
# 模型列表:
# 1. ZoneTemp               - 温区温度数据
# 2. HopperData             - 料仓数据
# 3. RollerKilnRealtime     - 辊道窑实时数据
# 4. RotaryKilnRealtime     - 回转窑实时数据
# 5. KilnHistoryQuery       - 历史数据查询参数
# 6. KilnHistoryResponse    - 历史数据查询响应
# ============================================================

from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional
from enum import Enum


# ------------------------------------------------------------
# 1. ZoneTemp - 温区温度数据
# ------------------------------------------------------------
class ZoneTemp(BaseModel):
    """温区温度数据"""
    zone_id: int = Field(..., description="温区ID")
    zone_name: str = Field(..., description="温区名称")
    temperature: float = Field(..., description="当前温度 °C")
    set_point: Optional[float] = Field(None, description="设定温度 °C")


# ------------------------------------------------------------
# 2. HopperData - 料仓数据
# ------------------------------------------------------------
class HopperData(BaseModel):
    """料仓数据"""
    hopper_id: int = Field(..., description="料仓ID")
    weight: float = Field(..., description="当前重量 kg")
    capacity: float = Field(..., description="总容量 kg")
    percent: float = Field(..., description="容量百分比 %")
    low_alarm: bool = Field(False, description="低重量告警状态")
    alarm_threshold: float = Field(..., description="告警阈值 kg")


# ------------------------------------------------------------
# 3. RollerKilnRealtime - 辊道窑实时数据
# ------------------------------------------------------------
class RollerKilnRealtime(BaseModel):
    """辊道窑实时数据"""
    timestamp: datetime = Field(..., description="数据时间戳")
    zones: List[ZoneTemp] = Field(..., description="多温区温度数据")
    voltage: float = Field(..., description="电压 V")
    current: float = Field(..., description="电流 A")
    power: float = Field(..., description="功率 kW")
    total_energy: float = Field(..., description="累计电量 kWh")
    status: bool = Field(..., description="运行状态")


# ------------------------------------------------------------
# 4. RotaryKilnRealtime - 回转窑实时数据
# ------------------------------------------------------------
class RotaryKilnRealtime(BaseModel):
    """回转窑实时数据"""
    timestamp: datetime = Field(..., description="数据时间戳")
    device_id: int = Field(..., ge=1, le=3, description="设备ID 1-3")
    device_name: str = Field(..., description="设备名称")
    zones: List[ZoneTemp] = Field(..., description="8温区温度数据")
    voltage: float = Field(..., description="电压 V")
    current: float = Field(..., description="电流 A")
    power: float = Field(..., description="功率 kW")
    total_energy: float = Field(..., description="累计电量 kWh")
    feed_speed: float = Field(..., description="下料速度 kg/h")
    hopper: HopperData = Field(..., description="料仓数据")
    status: bool = Field(..., description="运行状态")


# ------------------------------------------------------------
# 5. KilnHistoryQuery - 历史数据查询参数
# ------------------------------------------------------------
class QueryDimension(str, Enum):
    """查询维度"""
    HOUR = "hour"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class DataInterval(str, Enum):
    """数据间隔"""
    FIVE_SEC = "5s"
    ONE_MIN = "1m"
    FIVE_MIN = "5m"
    ONE_HOUR = "1h"
    ONE_DAY = "1d"


class KilnHistoryQuery(BaseModel):
    """历史数据查询参数"""
    start_time: datetime = Field(..., description="开始时间")
    end_time: datetime = Field(..., description="结束时间")
    interval: DataInterval = Field(DataInterval.ONE_MIN, description="数据间隔")
    dimension: Optional[QueryDimension] = Field(None, description="查询维度")
    zone_ids: Optional[List[int]] = Field(None, description="指定温区ID列表")


# ------------------------------------------------------------
# 6. KilnHistoryResponse - 历史数据查询响应
# ------------------------------------------------------------
class RollerKilnHistory(BaseModel):
    """辊道窑历史数据响应"""
    start_time: datetime
    end_time: datetime
    interval: str
    data: List[RollerKilnRealtime]


class RotaryKilnHistory(BaseModel):
    """回转窑历史数据响应"""
    device_id: int
    start_time: datetime
    end_time: datetime
    interval: str
    dimension: Optional[str] = None
    data: List[RotaryKilnRealtime]
