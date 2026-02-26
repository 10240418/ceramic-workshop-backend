# ============================================================
# 文件说明: ws_messages.py - WebSocket 消息模型
# ============================================================
# 消息类型:
#   - subscribe / unsubscribe: 客户端订阅/取消订阅
#   - heartbeat: 心跳消息
#   - realtime_data: 实时数据推送 (9台回转窑 + 辊道窑 + SCR/风机)
#   - device_status: 设备状态推送 (DB3/DB7/DB11 解析后数据)
#   - error: 错误消息
# ============================================================
# 支持频道:
#   - realtime: 实时传感器数据 (温度/功率/重量/流量等)
#   - device_status: 设备通信状态 (正常/故障)
# ============================================================

from typing import Optional, Dict, Any, Literal
from pydantic import BaseModel, Field


# ============================================================
# 客户端 -> 服务端消息
# ============================================================

class SubscribeMessage(BaseModel):
    """订阅消息"""
    type: Literal["subscribe"] = "subscribe"
    channel: Literal["realtime", "device_status"]


class UnsubscribeMessage(BaseModel):
    """取消订阅消息"""
    type: Literal["unsubscribe"] = "unsubscribe"
    channel: Literal["realtime", "device_status"]


class HeartbeatMessage(BaseModel):
    """心跳消息"""
    type: Literal["heartbeat"] = "heartbeat"
    timestamp: Optional[str] = None


# ============================================================
# 服务端 -> 客户端消息
# ============================================================

class RealtimeDataMessage(BaseModel):
    """实时数据推送消息
    
    包含: 9台回转窑 + 1台辊道窑(6温区+总表) + 2套SCR + 2台风机
    推送频率: 与 PLC 轮询同步 (约每 6 秒)
    """
    type: Literal["realtime_data"] = "realtime_data"
    success: bool = True
    timestamp: str = Field(..., description="ISO 8601 时间戳")
    source: Literal["plc", "mock"] = Field(default="plc", description="数据来源")
    data: Dict[str, Any] = Field(
        default_factory=dict,
        description="设备数据字典 {device_id: device_data}"
    )


class DeviceStatusMessage(BaseModel):
    """设备状态推送消息
    
    来源: DB3 (回转窑状态) + DB7 (辊道窑状态) + DB11 (SCR/风机状态)
    推送频率: 与 PLC 轮询同步 (约每 6 秒)
    """
    type: Literal["device_status"] = "device_status"
    success: bool = True
    timestamp: str = Field(..., description="ISO 8601 时间戳")
    source: Literal["plc", "mock"] = Field(default="plc", description="数据来源")
    data: Dict[str, Any] = Field(
        default_factory=dict,
        description="解析后的设备状态 {db3: [...], db7: [...], db11: [...]}"
    )
    summary: Dict[str, int] = Field(
        default_factory=dict,
        description="状态汇总 {total: N, normal: N, error: N}"
    )


class ErrorMessage(BaseModel):
    """错误消息"""
    type: Literal["error"] = "error"
    code: str = Field(..., description="错误码")
    message: str = Field(..., description="错误描述")


# ============================================================
# 错误码枚举
# ============================================================

class ErrorCode:
    INVALID_MESSAGE = "INVALID_MESSAGE"
    INVALID_CHANNEL = "INVALID_CHANNEL"
    INTERNAL_ERROR = "INTERNAL_ERROR"
