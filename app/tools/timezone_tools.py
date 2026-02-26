# ============================================================
# 文件说明: timezone_tools.py - 时区工具模块
# ============================================================
# 统一使用北京时间 (UTC+8)
# ============================================================

from datetime import datetime, timezone, timedelta

# 北京时区 (UTC+8)
BEIJING_TZ = timezone(timedelta(hours=8))


def now_beijing() -> datetime:
    """获取当前北京时间"""
    return datetime.now(BEIJING_TZ)


def to_beijing(dt: datetime) -> datetime:
    """将任意时间转换为北京时间
    
    Args:
        dt: datetime对象（可以是UTC或其他时区）
    
    Returns:
        北京时间的datetime对象
    """
    if dt.tzinfo is None:
        # 如果没有时区信息，假设是UTC
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BEIJING_TZ)


def beijing_isoformat(dt: datetime = None) -> str:
    """获取北京时间的ISO格式字符串
    
    Args:
        dt: datetime对象，如果为None则使用当前时间
    
    Returns:
        ISO格式字符串，如 "2025-12-26T15:30:00+08:00"
    """
    if dt is None:
        dt = now_beijing()
    elif dt.tzinfo is None or dt.tzinfo == timezone.utc:
        dt = to_beijing(dt)
    return dt.isoformat()
