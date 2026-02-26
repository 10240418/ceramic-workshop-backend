"""
磨料车间统一命名工具

1. 统一数据库字段命名（保留旧字段兼容）
2. 统一前后端数据流字段命名
3. 统一设备分组别名
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List, Optional


# 1. 字段命名映射（旧字段 -> 新字段）
LEGACY_TO_CANONICAL_FIELD = {
    "Pt": "active_power_kw",
    "ImpEp": "active_energy_kwh",
    "Ua_0": "voltage_a_v",
    "Ua_1": "voltage_b_v",
    "Ua_2": "voltage_c_v",
    "I_0": "current_a_a",
    "I_1": "current_b_a",
    "I_2": "current_c_a",
    "temperature": "temperature_c",
    "feed_rate": "feed_rate_kgh",
    "weight": "weight_kg",
    "flow_rate": "gas_flow_rate_m3h",
    "total_flow": "gas_total_flow_m3",
}

# 2. 反向映射（新字段 -> 旧字段）
CANONICAL_TO_LEGACY_FIELD = {
    canonical: legacy for legacy, canonical in LEGACY_TO_CANONICAL_FIELD.items()
}


def normalize_fields(fields: Dict[str, Any]) -> Dict[str, Any]:
    """标准化字段命名：保留旧字段，同时补充新字段。"""
    merged = dict(fields)

    for legacy_key, canonical_key in LEGACY_TO_CANONICAL_FIELD.items():
        if legacy_key in merged and canonical_key not in merged:
            merged[canonical_key] = merged[legacy_key]
        elif canonical_key in merged and legacy_key not in merged:
            merged[legacy_key] = merged[canonical_key]

    return merged


def normalize_device_payload(device_data: Dict[str, Any]) -> Dict[str, Any]:
    """标准化单个设备 payload。"""
    normalized = deepcopy(device_data)
    modules = normalized.get("modules")

    if isinstance(modules, dict):
        for module in modules.values():
            if not isinstance(module, dict):
                continue
            fields = module.get("fields")
            if isinstance(fields, dict):
                module["fields"] = normalize_fields(fields)

    return normalized


def normalize_device_list(devices: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """标准化设备列表。"""
    return [normalize_device_payload(item) for item in devices]


def normalize_device_map(device_map: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """标准化设备字典（WebSocket realtime_data.data 结构）。"""
    return {k: normalize_device_payload(v) for k, v in device_map.items()}


def map_history_fields(fields: Optional[List[str]]) -> Optional[List[str]]:
    """历史查询字段映射：允许前端传新字段名，自动映射到旧字段。"""
    if not fields:
        return fields
    return [CANONICAL_TO_LEGACY_FIELD.get(field, field) for field in fields]




def parse_history_fields(
    fields,
    module_type=None,
):
    """解析历史查询的字段参数并映射到数据库存储字段名

    Args:
        fields: 逗号分隔的字段字符串。传 None 或空字符串表示查全部。
        module_type: 模块类型（保留参数供后续扩展）。

    Returns:
        字段名列表，或 None。
    """
    if not fields:
        return None

    raw_list = [f.strip() for f in fields.split(",") if f.strip()]
    if not raw_list:
        return None

    return map_history_fields(raw_list)


def add_group_aliases(payload: Dict[str, Any]) -> Dict[str, Any]:
    """补充统一设备分组别名（保留旧分组键）。"""
    normalized = deepcopy(payload)

    if "scr" in normalized and "ammonia_pump" not in normalized:
        normalized["ammonia_pump"] = normalized["scr"]

    if "fan" in normalized and "induced_draft_fan" not in normalized:
        normalized["induced_draft_fan"] = normalized["fan"]

    return normalized
