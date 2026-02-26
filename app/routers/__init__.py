# ============================================================
# Routers Package - API 路由模块
# ============================================================
# 路由列表:
# - health:       健康检查 (/api/health, /api/ws/status)
# - config:       系统配置 (/api/config)
# - hopper:       料仓设备 (/api/hopper)
# - roller:       辊道窑设备 (/api/roller)
# - scr_fan:      SCR和风机设备 (/api/scr, /api/fan)
# - status:       传感器状态位 (/api/status)
# - devices:      设备列表 (/api/devices)
# - export:       数据导出 (/api/export)
# - daily_summary:日汇总 (/api/daily-summary)
# - websocket:    WebSocket 实时推送 (/ws/realtime)
# ============================================================

from . import health
from . import config
from . import hopper
from . import roller
from . import scr_fan
from . import status
from . import devices
from . import export
from . import daily_summary
from . import websocket

__all__ = [
    'health', 'config', 'hopper', 'roller', 'scr_fan',
    'status', 'devices', 'export', 'daily_summary', 'websocket',
]
