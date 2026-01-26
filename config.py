# ============================================================
# 文件说明: config.py - 应用配置管理
# ============================================================
# 使用 pydantic-settings 管理配置，支持环境变量和配置文件
# 数据库架构: 仅使用 InfluxDB (时序数据) + YAML 文件 (配置数据)
# ============================================================

from functools import lru_cache
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """应用配置"""
    
    # 服务器配置
    server_host: str = "0.0.0.0"
    server_port: int = 8080
    debug: bool = True
    
    # 轮询开关 (用于docker部署时关闭轮询，由mock服务提供数据)
    enable_polling: bool = True
    
    # Mock模式 (使用模拟数据而非真实PLC)
    mock_mode: bool = False
    
    # 详细轮询日志 (True: 显示每个设备的详细数据, False: 仅显示写入数量)
    # Release模式下建议设为False，只输出error级别和API请求日志
    verbose_polling_log: bool = False
    
    # PLC 配置
    plc_ip: str = "192.168.50.223"
    plc_rack: int = 0
    plc_slot: int = 1
    plc_timeout: int = 5000  # ms
    plc_poll_interval: int = 6  # seconds (轮询间隔)
    
    # 批量写入配置
    # 🔧 [CRITICAL] 从30降到10，减少批量写入的数据量
    # 每次轮询约46个数据点，10次=460点
    batch_write_size: int = 10  # 多少次轮询后批量写入 InfluxDB
    
    # 本地缓存配置
    local_cache_path: str = "data/cache.db"  # SQLite 缓存文件路径
    
    # InfluxDB 配置 (唯一数据库)
    influx_url: str = "http://localhost:8086"
    influx_token: str = "ceramic-workshop-token"
    influx_org: str = "ceramic-workshop"
    influx_bucket: str = "sensor_data"
    
    # 配置文件路径
    config_dir: str = "configs"
    sensors_config_file: str = "configs/sensors.yaml"
    devices_config_file: str = "configs/devices.yaml"
    
    # JWT 配置 (可选，用于后续认证)

    secret_key: str = "ceramic-workshop-dev-only-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24小时
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# ------------------------------------------------------------
# 获取配置单例
# ------------------------------------------------------------
@lru_cache()
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()
