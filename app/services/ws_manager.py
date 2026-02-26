# ============================================================
# 文件说明: ws_manager.py - WebSocket 连接管理器
# ============================================================
# 方法列表:
#   1. connect()              - 接受新的 WebSocket 连接
#   2. disconnect()           - 移除 WebSocket 连接
#   3. subscribe()            - 订阅频道 (realtime | device_status)
#   4. unsubscribe()          - 取消订阅频道
#   5. update_heartbeat()     - 更新客户端心跳时间
#   6. broadcast()            - 向指定频道广播消息
#   7. send_personal()        - 发送消息给单个客户端
#   8. start_push_tasks()     - 启动后台推送任务
#   9. stop_push_tasks()      - 停止后台推送任务
# ============================================================
# 支持频道:
#   - realtime: 实时传感器数据 (9台回转窑 + 辊道窑 + SCR/风机)
#   - device_status: 设备通信状态 (DB3/DB7/DB11 解析后数据)
# ============================================================

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Set, Optional

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

HEARTBEAT_TIMEOUT = 45    # 心跳超时时间 (秒)
_EVENT_WAIT_TIMEOUT = 10.0  # 等待新数据超时 (超时后继续循环检查)


class ConnectionManager:
    """WebSocket 连接管理器 (单例)"""

    def __init__(self):
        # websocket -> 订阅的频道集合
        self.active_connections: Dict[WebSocket, Set[str]] = {}
        # websocket -> 最后心跳时间
        self.last_heartbeat: Dict[WebSocket, datetime] = {}
        # 推送任务句柄 (按频道独立)
        self._push_realtime_task: Optional[asyncio.Task] = None
        self._push_status_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._is_running = False
        # 推送计数器 (每 50 次输出一次摘要日志)
        self._push_count = 0
        self._push_log_interval = 50

    # ------------------------------------------------------------
    # 1. connect() - 接受新的 WebSocket 连接
    # ------------------------------------------------------------
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[websocket] = set()
        self.last_heartbeat[websocket] = datetime.now(timezone.utc)
        client_host = websocket.client.host if websocket.client else "unknown"
        logger.info(
            f"[TEST][前端→WS] 新连接建立 | 来自={client_host} | "
            f"当前连接数={len(self.active_connections)}"
        )

    # ------------------------------------------------------------
    # 2. disconnect() - 移除 WebSocket 连接
    # ------------------------------------------------------------
    def disconnect(self, websocket: WebSocket):
        channels = self.active_connections.get(websocket, set())
        if websocket in self.active_connections:
            del self.active_connections[websocket]
        if websocket in self.last_heartbeat:
            del self.last_heartbeat[websocket]
        logger.info(
            f"[WS] 连接断开 (频道: {channels or '无'})，"
            f"剩余连接数: {len(self.active_connections)}"
        )

    # ------------------------------------------------------------
    # 3. subscribe() - 订阅频道
    # ------------------------------------------------------------
    def subscribe(self, websocket: WebSocket, channel: str) -> bool:
        valid_channels = {"realtime", "device_status"}
        if channel not in valid_channels:
            logger.warning(f"[WS] 无效的订阅频道: {channel}")
            return False
        if websocket in self.active_connections:
            self.active_connections[websocket].add(channel)
            subs = self.get_channel_subscribers(channel)
            logger.info(f"[TEST][前端→WS] 订阅频道 [{channel}] | 该频道订阅数={subs}")
            return True
        return False

    # ------------------------------------------------------------
    # 4. unsubscribe() - 取消订阅频道
    # ------------------------------------------------------------
    def unsubscribe(self, websocket: WebSocket, channel: str):
        if websocket in self.active_connections:
            self.active_connections[websocket].discard(channel)
            logger.info(f"[WS] 取消订阅频道: {channel}")

    # ------------------------------------------------------------
    # 5. update_heartbeat() - 更新客户端心跳时间
    # ------------------------------------------------------------
    def update_heartbeat(self, websocket: WebSocket):
        self.last_heartbeat[websocket] = datetime.now(timezone.utc)
        logger.debug(f"[WS] 收到心跳，连接数: {len(self.active_connections)}")

    def get_connection_count(self) -> int:
        """获取当前连接数"""
        return len(self.active_connections)

    def get_channel_subscribers(self, channel: str) -> int:
        """获取指定频道的订阅者数量"""
        return sum(1 for ch in self.active_connections.values() if channel in ch)

    # ------------------------------------------------------------
    # 6. broadcast() - 向指定频道广播消息
    # ------------------------------------------------------------
    async def broadcast(self, channel: str, message: dict):
        disconnected = []
        for ws, channels in self.active_connections.items():
            if channel not in channels:
                continue
            try:
                if (ws.application_state != WebSocketState.CONNECTED or
                        ws.client_state != WebSocketState.CONNECTED):
                    disconnected.append(ws)
                    continue
                await ws.send_json(message)
            except WebSocketDisconnect:
                disconnected.append(ws)
            except Exception as e:
                logger.warning(f"[WS] 发送消息失败: {e}")
                disconnected.append(ws)

        for ws in disconnected:
            self.disconnect(ws)

    # ------------------------------------------------------------
    # 7. send_personal() - 发送消息给单个客户端
    # ------------------------------------------------------------
    async def send_personal(self, websocket: WebSocket, message: dict):
        try:
            if (websocket.application_state != WebSocketState.CONNECTED or
                    websocket.client_state != WebSocketState.CONNECTED):
                self.disconnect(websocket)
                return
            await websocket.send_json(message)
        except WebSocketDisconnect:
            self.disconnect(websocket)
        except Exception as e:
            logger.warning(f"[WS] 发送消息失败: {e}")
            self.disconnect(websocket)

    # ============================================================
    # 后台推送任务
    # ============================================================

    # ------------------------------------------------------------
    # 8. start_push_tasks() - 启动后台推送任务
    # ------------------------------------------------------------
    async def start_push_tasks(self):
        if self._is_running:
            return
        self._is_running = True
        self._push_realtime_task = asyncio.create_task(
            self._push_realtime_loop(), name="ws_push_realtime"
        )
        self._push_status_task = asyncio.create_task(
            self._push_status_loop(), name="ws_push_status"
        )
        self._cleanup_task = asyncio.create_task(
            self._cleanup_loop(), name="ws_cleanup_loop"
        )
        logger.info(f"[WS] 推送任务已启动 (心跳超时: {HEARTBEAT_TIMEOUT}s, 双频道独立任务)")

    # ------------------------------------------------------------
    # 9. stop_push_tasks() - 停止后台推送任务
    # ------------------------------------------------------------
    async def stop_push_tasks(self):
        self._is_running = False
        for task in [self._push_realtime_task, self._push_status_task, self._cleanup_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._push_realtime_task = None
        self._push_status_task = None
        self._cleanup_task = None
        logger.info("[WS] 推送任务已停止")

    async def _push_realtime_loop(self):
        """realtime 频道独立推送循环 (仅在 DB8/9/10 有新数据时触发)"""
        from app.services.polling_service import get_realtime_updated_event
        event = get_realtime_updated_event()

        while self._is_running:
            try:
                # [TEST] 等待轮询服务通知
                await asyncio.wait_for(event.wait(), timeout=_EVENT_WAIT_TIMEOUT)
                event.clear()
                logger.info(f"[TEST][WS] 收到轮询服务通知，准备推送实时数据")

                timestamp = datetime.now(timezone.utc).isoformat()

                if self.get_channel_subscribers("realtime") > 0:
                    await self._push_realtime_data(timestamp)

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"[WS] realtime 推送任务异常: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def _push_status_loop(self):
        """device_status 频道独立推送循环 (仅在 DB3/7/11 有新数据时触发)"""
        from app.services.polling_service import get_status_updated_event
        event = get_status_updated_event()

        while self._is_running:
            try:
                await asyncio.wait_for(event.wait(), timeout=_EVENT_WAIT_TIMEOUT)
                event.clear()

                timestamp = datetime.now(timezone.utc).isoformat()

                if self.get_channel_subscribers("device_status") > 0:
                    await self._push_device_status(timestamp)

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"[WS] device_status 推送任务异常: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def _push_realtime_data(self, timestamp: str):
        """推送实时传感器数据到 realtime 频道"""
        from app.services.polling_service import get_latest_data

        latest = get_latest_data()
        if not latest:
            logger.debug("[WS] 内存缓存为空，跳过 realtime 推送")
            return

        source = "mock" if settings.mock_mode else "plc"
        
        # [TEST] 统计数据点数量
        hopper_count = sum(1 for k in latest.keys() if 'hopper' in k)
        roller_count = sum(1 for k in latest.keys() if 'roller_kiln' in k)
        scr_count = sum(1 for k in latest.keys() if 'scr' in k)
        fan_count = sum(1 for k in latest.keys() if 'fan' in k)
        
        logger.info(
            f"[TEST][WS→前端] 准备推送 | "
            f"料仓={hopper_count} | 辊道窑={roller_count} | SCR={scr_count} | 风机={fan_count} | "
            f"总设备={len(latest)} | 订阅者={self.get_channel_subscribers('realtime')}"
        )
        
        message = {
            "type": "realtime_data",
            "success": True,
            "timestamp": timestamp,
            "source": source,
            "data": latest,
        }
        await self.broadcast("realtime", message)
        
        logger.info(f"[TEST][WS→前端] 推送完成 | timestamp={timestamp}")

        self._push_count += 1
        if self._push_count % self._push_log_interval == 0:
            subs = self.get_channel_subscribers("realtime")
            device_count = len(latest)
            logger.info(
                f"[WS] 推送统计: 第{self._push_count}次，"
                f"订阅者={subs}，设备数={device_count}，source={source}"
            )

    async def _push_device_status(self, timestamp: str):
        """推送设备通信状态到 device_status 频道"""
        from app.services.polling_service import get_device_status_raw
        from app.plc.parser_device_status import get_device_status_parser

        raw_data = get_device_status_raw()
        if not raw_data:
            logger.debug("[WS] 设备状态缓存为空，跳过 device_status 推送")
            return

        try:
            parser = get_device_status_parser()
            parsed_data = parser.parse_all(raw_data)
            all_statuses = [s for db_list in parsed_data.values() for s in db_list]
            total = len(all_statuses)
            normal = sum(1 for s in all_statuses if s.get("is_normal", False))
            summary = {"total": total, "normal": normal, "error": total - normal}
        except Exception as e:
            logger.error(f"[WS] 设备状态解析失败: {e}", exc_info=True)
            return

        source = "mock" if settings.mock_mode else "plc"
        message = {
            "type": "device_status",
            "success": True,
            "timestamp": timestamp,
            "source": source,
            "data": parsed_data,
            "summary": summary,
        }
        await self.broadcast("device_status", message)

    async def _cleanup_loop(self):
        """清理超时连接的后台循环"""
        while self._is_running:
            await asyncio.sleep(10)

            now = datetime.now(timezone.utc)
            disconnected = []

            for ws, last_hb in self.last_heartbeat.items():
                delta = (now - last_hb).total_seconds()
                if delta > HEARTBEAT_TIMEOUT:
                    logger.warning(f"[WS] 心跳超时 ({delta:.0f}s)，断开连接")
                    disconnected.append(ws)

            for ws in disconnected:
                try:
                    await ws.close(code=1000, reason="Heartbeat timeout")
                except Exception:
                    pass
                self.disconnect(ws)

            # 清理已断开但未正确移除的僵尸连接
            stale = [
                ws for ws in self.active_connections
                if (ws.application_state != WebSocketState.CONNECTED or
                    ws.client_state != WebSocketState.CONNECTED)
            ]
            for ws in stale:
                logger.warning("[WS] 清理僵尸连接")
                self.disconnect(ws)


# ============================================================
# 全局单例
# ============================================================
_manager: Optional[ConnectionManager] = None


def get_ws_manager() -> ConnectionManager:
    """获取 WebSocket 连接管理器单例"""
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
    return _manager
