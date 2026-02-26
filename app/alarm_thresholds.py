# ============================================================
# 文件说明: alarm_thresholds.py - 报警阈值模型与管理器
# ============================================================
# 方法列表:
# 1. ThresholdConfig         - 单参数阈值数据类
# 2. AlarmThresholds         - 全量阈值配置数据类 (30个参数)
# 3. AlarmThresholdManager   - 单例管理器，负责加载/保存/检查
# ============================================================
import json
import os
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

_THRESHOLDS_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "alarm_thresholds.json")


@dataclass
class ThresholdConfig:
    warning_max: float   # 超过此值 -> 警告 (黄色)
    alarm_max: float     # 超过此值 -> 报警 (红色)
    enabled: bool = True


def _tc(warning: float, alarm: float) -> ThresholdConfig:
    return ThresholdConfig(warning_max=warning, alarm_max=alarm)


@dataclass
class AlarmThresholds:
    # --------------------------------------------------------
    # 回转窑温度 x9  (short_hopper x4, no_hopper x2, long_hopper x3)
    # --------------------------------------------------------
    rotary_temp_short_hopper_1: ThresholdConfig = field(default_factory=lambda: _tc(900, 1100))
    rotary_temp_short_hopper_2: ThresholdConfig = field(default_factory=lambda: _tc(900, 1100))
    rotary_temp_short_hopper_3: ThresholdConfig = field(default_factory=lambda: _tc(900, 1100))
    rotary_temp_short_hopper_4: ThresholdConfig = field(default_factory=lambda: _tc(900, 1100))
    rotary_temp_no_hopper_1:    ThresholdConfig = field(default_factory=lambda: _tc(900, 1100))
    rotary_temp_no_hopper_2:    ThresholdConfig = field(default_factory=lambda: _tc(900, 1100))
    rotary_temp_long_hopper_1:  ThresholdConfig = field(default_factory=lambda: _tc(900, 1100))
    rotary_temp_long_hopper_2:  ThresholdConfig = field(default_factory=lambda: _tc(900, 1100))
    rotary_temp_long_hopper_3:  ThresholdConfig = field(default_factory=lambda: _tc(900, 1100))

    # --------------------------------------------------------
    # 回转窑功率 x9
    # --------------------------------------------------------
    rotary_power_short_hopper_1: ThresholdConfig = field(default_factory=lambda: _tc(80, 100))
    rotary_power_short_hopper_2: ThresholdConfig = field(default_factory=lambda: _tc(80, 100))
    rotary_power_short_hopper_3: ThresholdConfig = field(default_factory=lambda: _tc(80, 100))
    rotary_power_short_hopper_4: ThresholdConfig = field(default_factory=lambda: _tc(80, 100))
    rotary_power_no_hopper_1:    ThresholdConfig = field(default_factory=lambda: _tc(80, 100))
    rotary_power_no_hopper_2:    ThresholdConfig = field(default_factory=lambda: _tc(80, 100))
    rotary_power_long_hopper_1:  ThresholdConfig = field(default_factory=lambda: _tc(80, 100))
    rotary_power_long_hopper_2:  ThresholdConfig = field(default_factory=lambda: _tc(80, 100))
    rotary_power_long_hopper_3:  ThresholdConfig = field(default_factory=lambda: _tc(80, 100))

    # --------------------------------------------------------
    # 辊道窑温度 x6
    # --------------------------------------------------------
    roller_temp_zone1: ThresholdConfig = field(default_factory=lambda: _tc(1150, 1350))
    roller_temp_zone2: ThresholdConfig = field(default_factory=lambda: _tc(1150, 1350))
    roller_temp_zone3: ThresholdConfig = field(default_factory=lambda: _tc(1150, 1350))
    roller_temp_zone4: ThresholdConfig = field(default_factory=lambda: _tc(1150, 1350))
    roller_temp_zone5: ThresholdConfig = field(default_factory=lambda: _tc(1150, 1350))
    roller_temp_zone6: ThresholdConfig = field(default_factory=lambda: _tc(1150, 1350))

    # --------------------------------------------------------
    # 风机功率 x2
    # --------------------------------------------------------
    fan_power_1: ThresholdConfig = field(default_factory=lambda: _tc(60, 80))
    fan_power_2: ThresholdConfig = field(default_factory=lambda: _tc(60, 80))

    # --------------------------------------------------------
    # SCR 氨水泵功率 x2
    # --------------------------------------------------------
    scr_power_1: ThresholdConfig = field(default_factory=lambda: _tc(30, 50))
    scr_power_2: ThresholdConfig = field(default_factory=lambda: _tc(30, 50))

    # --------------------------------------------------------
    # SCR 燃气表流量 x2
    # --------------------------------------------------------
    scr_gas_1: ThresholdConfig = field(default_factory=lambda: _tc(100, 150))
    scr_gas_2: ThresholdConfig = field(default_factory=lambda: _tc(100, 150))


class AlarmThresholdManager:
    _instance: Optional["AlarmThresholdManager"] = None

    def __init__(self):
        self.thresholds = AlarmThresholds()
        self._load()

    @classmethod
    def get_instance(cls) -> "AlarmThresholdManager":
        if cls._instance is None:
            cls._instance = AlarmThresholdManager()
        return cls._instance

    # --------------------------------------------------------
    # 1. 加载阈值配置
    # --------------------------------------------------------
    def _load(self):
        path = os.path.abspath(_THRESHOLDS_FILE)
        if not os.path.exists(path):
            logger.info("[AlarmThresh] 配置文件不存在，使用默认阈值: %s", path)
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            for param_name, cfg in raw.items():
                if hasattr(self.thresholds, param_name):
                    setattr(self.thresholds, param_name, ThresholdConfig(
                        warning_max=cfg.get("warning_max", 0),
                        alarm_max=cfg.get("alarm_max", 0),
                        enabled=cfg.get("enabled", True),
                    ))
            logger.info("[AlarmThresh] 阈值配置加载完成，共 %d 个参数", len(raw))
        except Exception as e:
            logger.error("[AlarmThresh] 加载失败，使用默认值: %s", e)

    # --------------------------------------------------------
    # 2. 保存阈值配置
    # --------------------------------------------------------
    def save(self, data: dict) -> bool:
        """
        接收前端推送的 {param_name: {warning_max, alarm_max, enabled}} 字典，
        更新内存并持久化到 JSON 文件。
        """
        updated = 0
        for param_name, cfg in data.items():
            if hasattr(self.thresholds, param_name):
                setattr(self.thresholds, param_name, ThresholdConfig(
                    warning_max=float(cfg.get("warning_max", 0)),
                    alarm_max=float(cfg.get("alarm_max", 0)),
                    enabled=bool(cfg.get("enabled", True)),
                ))
                updated += 1
        try:
            path = os.path.abspath(_THRESHOLDS_FILE)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            out = {}
            for k, v in asdict(self.thresholds).items():
                out[k] = v
            with open(path, "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, indent=2)
            logger.info("[AlarmThresh] 阈值配置保存完成，更新 %d 个参数", updated)
            return True
        except Exception as e:
            logger.error("[AlarmThresh] 保存失败: %s", e)
            return False

    # --------------------------------------------------------
    # 3. 获取全量阈值字典
    # --------------------------------------------------------
    def get_all(self) -> dict:
        return asdict(self.thresholds)

    # --------------------------------------------------------
    # 4. 检查单个值的报警级别
    # --------------------------------------------------------
    def check_value(self, param_name: str, value: float) -> str:
        """
        返回:
          'normal'  - 正常 (value <= warning_max)
          'warning' - 警告 (warning_max < value <= alarm_max)
          'alarm'   - 报警 (value > alarm_max)
        """
        cfg: Optional[ThresholdConfig] = getattr(self.thresholds, param_name, None)
        if cfg is None or not cfg.enabled:
            return "normal"
        if value > cfg.alarm_max:
            return "alarm"
        if value > cfg.warning_max:
            return "warning"
        return "normal"
