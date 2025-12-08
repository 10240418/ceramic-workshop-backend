# ============================================================
# 文件说明: polling_service.py - 数据轮询服务
# ============================================================
# 方法列表:
# 1. start_polling()        - 启动数据轮询任务
# 2. stop_polling()         - 停止数据轮询任务
# 3. _poll_data()           - 轮询数据并写入数据库
# 4. _poll_plc_data()       - [私有] 轮询真实PLC数据
# ============================================================

import asyncio
from datetime import datetime
from typing import Optional

from config import get_settings
from app.core.influxdb import write_point

settings = get_settings()

# 轮询任务句柄
_polling_task: Optional[asyncio.Task] = None
_is_running = False


# ------------------------------------------------------------
# 1. start_polling() - 启动数据轮询任务
# ------------------------------------------------------------
async def start_polling():
    """启动数据轮询任务"""
    global _polling_task, _is_running
    
    if _is_running:
        return
    
    _is_running = True
    _polling_task = asyncio.create_task(_poll_data())
    print(f"✅ Polling started (interval: {settings.plc_poll_interval}s)")


# ------------------------------------------------------------
# 2. stop_polling() - 停止数据轮询任务
# ------------------------------------------------------------
async def stop_polling():
    """停止数据轮询任务"""
    global _polling_task, _is_running
    
    _is_running = False
    if _polling_task:
        _polling_task.cancel()
        try:
            await _polling_task
        except asyncio.CancelledError:
            pass
    print("⏹️ Polling stopped")


# ------------------------------------------------------------
# 3. _poll_data() - 轮询数据并写入数据库
# ------------------------------------------------------------
async def _poll_data():
    """轮询数据并写入InfluxDB"""
    while _is_running:
        try:
            timestamp = datetime.now()
            # 从PLC读取数据
            await _poll_plc_data(timestamp)
            
        except Exception as e:
            print(f"❌ Polling error: {e}")
        
        await asyncio.sleep(settings.plc_poll_interval)



async def _poll_plc_data(timestamp: datetime):
    """从PLC读取真实数据"""
    from app.services.plc_service import PLCService
    
    plc_service = PLCService()
    
    try:
        # 辊道窑数据
        roller_data = plc_service.read_roller_kiln_data()
        # TODO: 根据实际传感器配置写入InfluxDB
        
        # 回转窑数据
        for device_id in [1, 2, 3]:
            rotary_data = plc_service.read_rotary_kiln_data(device_id)
            # TODO: 根据实际传感器配置写入InfluxDB
        
        # SCR设备数据
        for device_id in [1, 2]:
            scr_data = plc_service.read_scr_data(device_id)
            # TODO: 根据实际传感器配置写入InfluxDB
    
    except Exception as e:
        print(f"❌ PLC读取失败: {e}")

