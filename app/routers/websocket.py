 # ============================================================
# 文件说明: websocket.py - WebSocket 实时推送端点
# ============================================================
# 端点:
#   ws://localhost:8080/ws/realtime
# ============================================================
# 支持的客户端消息:
#   - {"type": "subscribe", "channel": "realtime"}
#   - {"type": "subscribe", "channel": "device_status"}
#   - {"type": "unsubscribe", "channel": "realtime"}
#   - {"type": "heartbeat", "timestamp": "..."}
# ============================================================
# 服务端推送消息类型:
#   - realtime_data: 9台回转窑 + 辊道窑 + SCR + 风机实时数据
#   - device_status: DB3/DB7/DB11 设备通信状态
#   - heartbeat: 心跳响应
#   - error: 错误消息
# ============================================================

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.ws_manager import get_ws_manager
from app.models.ws_messages import ErrorCode

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WebSocket"])


@router.websocket("/realtime")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket 实时数据端点

    端点: ws://localhost:8080/ws/realtime

    订阅实时传感器数据:
        {"type": "subscribe", "channel": "realtime"}

    订阅设备通信状态:
        {"type": "subscribe", "channel": "device_status"}

    心跳保活 (每 15s 发送一次):
        {"type": "heartbeat", "timestamp": "2026-02-24T10:30:00Z"}
    """
    manager = get_ws_manager()
    await manager.connect(websocket)

    try:
        while True:
            # 接收客户端消息
            try:
                data = await websocket.receive_json()
                logger.debug(f"[WS] 收到消息: {data}")
            except WebSocketDisconnect:
                logger.info("[WS] 客户端主动断开连接")
                break
            except Exception as e:
                err_str = str(e)
                logger.warning(f"[WS] 接收消息失败: {e}")
                # WebSocket 已关闭，退出循环，不再重试
                if "not connected" in err_str.lower() or "accept" in err_str.lower():
                    break
                try:
                    await manager.send_personal(websocket, {
                        "type": "error",
                        "code": ErrorCode.INVALID_MESSAGE,
                        "message": "无效的 JSON 消息格式",
                    })
                except Exception:
                    break
                continue

            msg_type = data.get("type")

            # 处理订阅请求
            if msg_type == "subscribe":
                channel = data.get("channel")
                logger.info(f"[WS] 收到订阅请求: {channel}")
                if not manager.subscribe(websocket, channel):
                    await manager.send_personal(websocket, {
                        "type": "error",
                        "code": ErrorCode.INVALID_CHANNEL,
                        "message": f"无效的频道: {channel}，支持: realtime, device_status",
                    })

            # 处理取消订阅
            elif msg_type == "unsubscribe":
                channel = data.get("channel")
                manager.unsubscribe(websocket, channel)

            # 处理心跳
            elif msg_type == "heartbeat":
                manager.update_heartbeat(websocket)
                await manager.send_personal(websocket, {
                    "type": "heartbeat",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

            # 未知消息类型
            else:
                logger.warning(f"[WS] 未知消息类型: {msg_type}")
                await manager.send_personal(websocket, {
                    "type": "error",
                    "code": ErrorCode.INVALID_MESSAGE,
                    "message": f"未知的消息类型: {msg_type}",
                })

    except Exception as e:
        logger.error(f"[WS] 连接异常: {e}", exc_info=True)
    finally:
        manager.disconnect(websocket)
