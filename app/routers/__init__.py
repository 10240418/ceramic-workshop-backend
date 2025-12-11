# ============================================================
# Routers Package - API 路由模块
# ============================================================
# 路由列表:
# - health: 健康检查 (/api/health)
# - config: 系统配置 (/api/config)
# - hopper: 料仓设备 (/api/hopper)
# - roller: 辊道窑设备 (/api/roller)
# - scr_fan: SCR和风机设备 (/api/scr, /api/fan)
# ============================================================

from . import health
from . import config
from . import hopper
from . import roller
from . import scr_fan

__all__ = ['health', 'config', 'hopper', 'roller', 'scr_fan']
