# ============================================================
# 文件说明: alarm_checker.py - 报警检查逻辑
# ============================================================
# 方法列表:
# 1. check_device_alarm()       - 统一入口，按 device_type 分发
# 2. _check_hopper_alarm()      - 回转窑（温度+功率）
# 3. _check_roller_kiln_alarm() - 辊道窑（6温区温度）
# 4. _check_fan_alarm()         - 风机（功率）
# 5. _check_scr_alarm()         - SCR氨水泵（功率+燃气流量）
# 6. _check_one()               - 单值检查并写入报警
# ============================================================
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from app.alarm_thresholds import AlarmThresholdManager
from app.core.alarm_store import log_alarm

logger = logging.getLogger(__name__)

_HOPPER_TYPES = {"short_hopper", "no_hopper", "long_hopper"}


# ------------------------------------------------------------
# 1. check_device_alarm() - 统一入口
# ------------------------------------------------------------
def check_device_alarm(
    device_id: str,
    device_type: str,
    modules_data: Dict[str, Any],
    timestamp: Optional[datetime] = None,
) -> None:
    """
    根据 device_type 分发报警检查。
    由 polling_service._update_latest_data() 调用，异常不向上传播。
    modules_data 结构:
      { tag: {"module_type": str, "fields": {field: value}} }
    例:
      {"temp": {"module_type":"TemperatureSensor", "fields":{"temperature":860.0}},
       "meter": {"module_type":"ElectricityMeter", "fields":{"Pt":75.0, ...}}}
    """
    try:
        if device_type in _HOPPER_TYPES:
            _check_hopper_alarm(device_id, modules_data, timestamp)
        elif device_type == "roller_kiln":
            _check_roller_kiln_alarm(modules_data, timestamp)
        elif device_type == "fan":
            _check_fan_alarm(device_id, modules_data, timestamp)
        elif device_type == "scr":
            _check_scr_alarm(device_id, modules_data, timestamp)
    except Exception as e:
        logger.error(
            "[AlarmChecker] 检查失败 device_id=%s device_type=%s: %s",
            device_id, device_type, e, exc_info=True,
        )


# ------------------------------------------------------------
# 2. _check_hopper_alarm() - 回转窑（温度 + 功率）
# ------------------------------------------------------------
def _check_hopper_alarm(
    device_id: str,
    modules_data: Dict[str, Any],
    timestamp: Optional[datetime],
) -> None:
    # 2.1 温度检查 (TemperatureSensor -> tag: "temp")
    temp_mod = modules_data.get("temp", {})
    if temp_mod.get("module_type") == "TemperatureSensor":
        temp = temp_mod.get("fields", {}).get("temperature")
        if temp is not None:
            _check_one(
                device_id=device_id,
                alarm_type="temperature",
                param_name=f"rotary_temp_{device_id}",
                value=temp,
                unit="°C",
                timestamp=timestamp,
            )

    # 2.2 功率检查 (ElectricityMeter -> tag: "meter")
    meter_mod = modules_data.get("meter", {})
    if meter_mod.get("module_type") == "ElectricityMeter":
        pt = meter_mod.get("fields", {}).get("Pt")
        if pt is not None:
            _check_one(
                device_id=device_id,
                alarm_type="power",
                param_name=f"rotary_power_{device_id}",
                value=pt,
                unit="kW",
                timestamp=timestamp,
            )


# ------------------------------------------------------------
# 3. _check_roller_kiln_alarm() - 辊道窑（6温区温度）
# ------------------------------------------------------------
def _check_roller_kiln_alarm(
    modules_data: Dict[str, Any],
    timestamp: Optional[datetime],
) -> None:
    # 辊道窑 device_id 固定为 roller_kiln_1，温区 tag: zone1_temp ~ zone6_temp
    for zone_num in range(1, 7):
        tag = f"zone{zone_num}_temp"
        mod = modules_data.get(tag, {})
        if mod.get("module_type") == "TemperatureSensor":
            temp = mod.get("fields", {}).get("temperature")
            if temp is not None:
                _check_one(
                    device_id="roller_kiln_1",
                    alarm_type="temperature",
                    param_name=f"roller_temp_zone{zone_num}",
                    value=temp,
                    unit="°C",
                    timestamp=timestamp,
                )


# ------------------------------------------------------------
# 4. _check_fan_alarm() - 风机（功率）
# ------------------------------------------------------------
def _check_fan_alarm(
    device_id: str,
    modules_data: Dict[str, Any],
    timestamp: Optional[datetime],
) -> None:
    # device_id: "fan_1" / "fan_2" -> param: "fan_power_1" / "fan_power_2"
    num = device_id.split("_")[-1]
    meter_mod = modules_data.get("meter", {})
    if meter_mod.get("module_type") == "ElectricityMeter":
        pt = meter_mod.get("fields", {}).get("Pt")
        if pt is not None:
            _check_one(
                device_id=device_id,
                alarm_type="power",
                param_name=f"fan_power_{num}",
                value=pt,
                unit="kW",
                timestamp=timestamp,
            )


# ------------------------------------------------------------
# 5. _check_scr_alarm() - SCR氨水泵（功率 + 燃气流量）
# ------------------------------------------------------------
def _check_scr_alarm(
    device_id: str,
    modules_data: Dict[str, Any],
    timestamp: Optional[datetime],
) -> None:
    # device_id: "scr_1" / "scr_2" -> param num "1" / "2"
    num = device_id.split("_")[-1]

    # 5.1 功率检查 (ElectricityMeter -> tag: "meter")
    meter_mod = modules_data.get("meter", {})
    if meter_mod.get("module_type") == "ElectricityMeter":
        pt = meter_mod.get("fields", {}).get("Pt")
        if pt is not None:
            _check_one(
                device_id=device_id,
                alarm_type="power",
                param_name=f"scr_power_{num}",
                value=pt,
                unit="kW",
                timestamp=timestamp,
            )

    # 5.2 燃气流量检查 (FlowMeter -> tag: "gas_meter")
    gas_mod = modules_data.get("gas_meter", {})
    if gas_mod.get("module_type") == "FlowMeter":
        flow = gas_mod.get("fields", {}).get("flow_rate")
        if flow is not None:
            _check_one(
                device_id=device_id,
                alarm_type="gas_flow",
                param_name=f"scr_gas_{num}",
                value=flow,
                unit="m3/h",
                timestamp=timestamp,
            )


# ------------------------------------------------------------
# 6. _check_one() - 单值检查并写入报警
# ------------------------------------------------------------
def _check_one(
    device_id: str,
    alarm_type: str,
    param_name: str,
    value: float,
    unit: str,
    timestamp: Optional[datetime],
) -> None:
    manager = AlarmThresholdManager.get_instance()
    level = manager.check_value(param_name, value)
    # 只记录报警级别，警告级别不写入数据库
    if level != "alarm":
        return

    cfg = getattr(manager.thresholds, param_name, None)
    threshold = cfg.alarm_max if level == "alarm" else cfg.warning_max
    message = (
        f"{param_name} = {value:.2f} {unit} "
        f"{'超过报警阈值' if level == 'alarm' else '超过警告阈值'} "
        f"{threshold:.2f} {unit}"
    )
    log_alarm(
        device_id=device_id,
        alarm_type=alarm_type,
        param_name=param_name,
        value=value,
        threshold=threshold,
        level=level,
        message=message,
        timestamp=timestamp,
    )
