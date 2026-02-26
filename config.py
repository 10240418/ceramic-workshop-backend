# ============================================================
# 文件说明: config.py - 应用配置管理
# ============================================================
# 使用 pydantic-settings 管理配置，支持环境变量和配置文件
# 数据库架构: 仅使用 InfluxDB (时序数据) + YAML 文件 (配置数据)
# ============================================================

from functools import lru_cache
from pathlib import Path
import sys
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


def _build_env_candidates() -> tuple[str, ...]:
    """构建 .env 候选路径（按优先级）

    优先级：
    1. 可执行文件所在目录（PyInstaller 打包后）
    2. 项目根目录（config.py 同级）
    3. 当前工作目录
    4. 启动脚本所在目录
    """
    project_dir = Path(__file__).resolve().parent
    candidates = []

    if getattr(sys, "frozen", False) and getattr(sys, "executable", None):
        candidates.append(Path(sys.executable).resolve().parent / ".env")

    candidates.append(project_dir / ".env")
    candidates.append(Path.cwd() / ".env")

    try:
        candidates.append(Path(sys.argv[0]).resolve().parent / ".env")
    except Exception:
        pass

    unique = []
    seen = set()
    for path in candidates:
        path_str = str(path)
        if path_str not in seen:
            seen.add(path_str)
            unique.append(path_str)

    return tuple(unique)


ENV_FILE_CANDIDATES = _build_env_candidates()


def get_active_env_file() -> Optional[str]:
    """返回实际命中的 .env 文件路径（若不存在则返回 None）"""
    for env_path in ENV_FILE_CANDIDATES:
        if Path(env_path).exists():
            return env_path
    return None


def get_runtime_base_dir() -> Path:
    """获取运行基目录（优先 exe 所在目录）"""
    if getattr(sys, "frozen", False) and getattr(sys, "executable", None):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resolve_runtime_path(path_value: str) -> str:
    """将相对路径转换为运行目录下的绝对路径"""
    path_obj = Path(path_value)
    if path_obj.is_absolute():
        return str(path_obj)
    return str((get_runtime_base_dir() / path_obj).resolve())


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
    mock_random_seed: Optional[int] = None  # 固定随机种子，便于复现
    mock_error_rate: float = 0.03           # 状态位默认错误率
    mock_data_profile: str = "realistic"   # 数据模式: realistic/stable/aggressive/alarm_test
    # alarm_test: 周期性触发温度/功率峰值（约每8-20次轮询），用于验证报警记录系统
    
    # 详细轮询日志 (True: 显示每个设备的详细数据, False: 仅显示写入数量)
    # Release模式下建议设为False，只输出error级别和API请求日志
    verbose_polling_log: bool = False
    
    # PLC 配置
    plc_ip: str = "192.168.50.223"
    plc_rack: int = 0
    plc_slot: int = 1
    plc_timeout: int = 5000  # ms
    plc_poll_interval: float = 5.0  # seconds (轮询间隔，支持小数如 0.5)
    realtime_poll_interval: float = 5.0  # seconds (实时数据轮询间隔)
    status_poll_interval: float = 5.0  # seconds (状态位轮询间隔)
    
    # 批量写入配置
    #  [CRITICAL] 从30降到10，减少批量写入的数据量
    # 每次轮询约46个数据点，10次=460点
    batch_write_size: int = 10  # 多少次轮询后批量写入 InfluxDB

    # 投料分析算法配置
    # feeding_window_size: 滑动窗口最大长度 (单位: 次轮询)
    # feeding_calc_interval: 每隔多少次轮询触发一次速度/累计量计算
    feeding_window_size: int = 36
    feeding_calc_interval: int = 12
    
    # 本地缓存配置
    local_cache_path: str = "data/cache.db"  # SQLite 缓存文件路径

    # 日志配置
    log_dir: str = "logs"
    log_file_name: str = "app.error.log"
    log_retention_days: int = 60
    log_level: str = "INFO"

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
    
    model_config = SettingsConfigDict(
        env_file=ENV_FILE_CANDIDATES,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("mock_random_seed", mode="before")
    @classmethod
    def _empty_seed_to_none(cls, value):
        if value in ("", None):
            return None
        return value

    @field_validator("log_retention_days")
    @classmethod
    def _validate_log_retention_days(cls, value: int) -> int:
        if value < 1:
            raise ValueError("log_retention_days 必须大于等于 1")
        return value

    @field_validator("feeding_window_size")
    @classmethod
    def _validate_feeding_window_size(cls, value: int) -> int:
        if value < 6 or value > 3600:
            raise ValueError("feeding_window_size 必须在 6 ~ 3600 之间")
        return value

    @field_validator("feeding_calc_interval")
    @classmethod
    def _validate_feeding_calc_interval(cls, value: int) -> int:
        if value < 1 or value > 3600:
            raise ValueError("feeding_calc_interval 必须在 1 ~ 3600 之间")
        return value

    @field_validator("local_cache_path", "log_dir", "config_dir", mode="before")
    @classmethod
    def _resolve_runtime_relative_path(cls, value: str) -> str:
        if value in ("", None):
            return value
        return resolve_runtime_path(value)


# ------------------------------------------------------------
# 获取配置单例
# ------------------------------------------------------------
@lru_cache()
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()
