# ============================================================
# 文件说明: scr.py - SCR设备数据模型
# ============================================================
# 模型列表:
# 1. FanData                - 风机数据
# 2. PumpData               - 氨水泵数据
# 3. GasPipelineData        - 燃气管路数据
# 4. SCRRealtime            - SCR设备实时数据
# 5. SCRHistoryQuery        - 历史数据查询参数
# 6. SCRHistoryResponse     - 历史数据查询响应
# ============================================================

from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional
from enum import Enum


# ------------------------------------------------------------
# 1. FanData - 风机数据
# ------------------------------------------------------------
class FanData(BaseModel):
    """风机数据"""
    fan_id: int = Field(..., description="风机ID")
    fan_name: str = Field(..., description="风机名称")
    power: float = Field(..., description="功率 kW")
    cumulative_energy: float = Field(..., description="累计电量 kWh")
    daily_energy: float = Field(0, description="日累计电量 kWh")
    monthly_energy: float = Field(0, description="月累计电量 kWh")
    yearly_energy: float = Field(0, description="年累计电量 kWh")
    status: bool = Field(..., description="运行状态 true=运行")


# ------------------------------------------------------------
# 2. PumpData - 氨水泵数据
# ------------------------------------------------------------
class PumpData(BaseModel):
    """氨水泵数据"""
    pump_id: int = Field(..., description="水泵ID")
    pump_name: str = Field(..., description="水泵名称")
    power: float = Field(..., description="功率 kW")
    cumulative_energy: float = Field(..., description="累计电量 kWh")
    daily_energy: float = Field(0, description="日累计电量 kWh")
    monthly_energy: float = Field(0, description="月累计电量 kWh")
    yearly_energy: float = Field(0, description="年累计电量 kWh")
    status: bool = Field(..., description="运行状态 true=运行")


# ------------------------------------------------------------
# 3. GasPipelineData - 燃气管路数据
# ------------------------------------------------------------
class GasPipelineData(BaseModel):
    """燃气管路数据"""
    pipeline_id: int = Field(..., ge=1, le=2, description="管路ID 1或2")
    pipeline_name: str = Field(..., description="管路名称")
    flow_rate: float = Field(..., description="当前流速 m³/h")
    cumulative_volume: float = Field(..., description="累计用量 m³")
    daily_volume: float = Field(0, description="日累计用量 m³")
    monthly_volume: float = Field(0, description="月累计用量 m³")
    yearly_volume: float = Field(0, description="年累计用量 m³")


# ------------------------------------------------------------
# 4. SCRRealtime - SCR设备实时数据
# ------------------------------------------------------------
class SCRRealtime(BaseModel):
    """SCR设备实时数据"""
    timestamp: datetime = Field(..., description="数据时间戳")
    device_id: int = Field(..., ge=1, le=2, description="设备ID 1-2")
    device_name: str = Field(..., description="设备名称")
    fans: List[FanData] = Field(..., description="风机数据列表")
    ammonia_pumps: List[PumpData] = Field(..., description="氨水泵数据列表")
    gas_pipelines: List[GasPipelineData] = Field(..., description="燃气管路数据")
    status: bool = Field(..., description="设备总运行状态")


# ------------------------------------------------------------
# 5. SCRHistoryQuery - 历史数据查询参数
# ------------------------------------------------------------
class StatisticsPeriod(str, Enum):
    """统计周期"""
    DAILY = "daily"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class EquipmentType(str, Enum):
    """设备类型"""
    FANS = "fans"
    PUMPS = "pumps"
    GAS = "gas"
    ALL = "all"


class SCRHistoryQuery(BaseModel):
    """SCR历史数据查询参数"""
    start_time: datetime = Field(..., description="开始时间")
    end_time: datetime = Field(..., description="结束时间")
    dimension: str = Field("hour", description="查询维度: hour/day/week/month/year")
    equipment_type: EquipmentType = Field(EquipmentType.ALL, description="设备类型筛选")


# ------------------------------------------------------------
# 6. SCRHistoryResponse - 历史数据查询响应
# ------------------------------------------------------------
class SCRHistory(BaseModel):
    """SCR历史数据响应"""
    device_ids: List[int] = Field(..., description="查询的设备ID列表")
    start_time: datetime
    end_time: datetime
    dimension: str
    data: List[SCRRealtime]


class EnergyStatistics(BaseModel):
    """能耗统计数据"""
    device_id: int
    equipment_id: int
    equipment_name: str
    period: str
    total_energy: float = Field(..., description="总能耗 kWh 或 m³")
    data_points: List[dict] = Field(..., description="统计数据点列表")
