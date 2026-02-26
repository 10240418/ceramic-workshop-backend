# ============================================================
# 文件说明: snap7_compat.py - python-snap7 版本校验
# ============================================================
# 固定要求版本: python-snap7 2.0.2
# ============================================================

from importlib.metadata import version as pkg_version
from typing import Optional, Tuple

# 硬编码要求版本
_REQUIRED_VERSION = "2.0.2"


def get_snap7_runtime_version() -> Optional[str]:
    """获取当前运行时 python-snap7 版本"""
    try:
        raw = pkg_version("python-snap7")
        parts = (raw or "").split(".")
        return ".".join(parts[:3]) if len(parts) >= 3 else raw
    except Exception:
        return None


def ensure_snap7_version() -> Tuple[bool, str]:
    """校验 python-snap7 版本是否为 2.0.2

    Returns:
        (is_valid, message)
    """
    runtime_version = get_snap7_runtime_version()
    if runtime_version is None:
        return False, "未检测到 python-snap7，请先安装: pip install python-snap7==2.0.2"

    if runtime_version == _REQUIRED_VERSION:
        return True, f"python-snap7 版本校验通过: {runtime_version}"

    return False, (
        f"python-snap7 版本不匹配，当前: {runtime_version}，要求: {_REQUIRED_VERSION}"
    )
