# ============================================================
# 文件说明: time_slice_tools.py - 时间切片工具
# ============================================================
# 功能:
# 1. 按北京时间自然日切分时间段（北京 0:00-23:59）
# 2. 区分完整天和不完整天
# 3. 支持跨天查询的智能切片
# ============================================================
# 方法列表:
# 1. split_time_range_by_natural_days()  - 按北京自然日切分时间段
# 2. is_full_day()                       - 判断是否为完整天
# 3. get_day_boundaries()                - 获取某天的边界时间（北京时区）
# ============================================================

from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Tuple

from app.tools.timezone_tools import BEIJING_TZ, to_beijing


class TimeSlice:
    """时间切片"""
    
    def __init__(
        self,
        start_time: datetime,
        end_time: datetime,
        date: str,
        is_full_day: bool,
        day_index: int
    ):
        self.start_time = start_time
        self.end_time = end_time
        self.date = date  # YYYY-MM-DD
        self.is_full_day = is_full_day
        self.day_index = day_index  # 从1开始
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "day": self.day_index,
            "date": self.date,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "is_full_day": self.is_full_day
        }


def split_time_range_by_natural_days(
    start_time: datetime,
    end_time: datetime
) -> List[TimeSlice]:
    """按北京时间自然日切分时间段
    
    **核心逻辑**:
    - 所有"天"边界基于北京时间 (UTC+8) 午夜
    - 完整天: 北京 0:00:00 ~ 23:59:59
    - 不完整天: 实际时间段
    - 内部全部使用 UTC 时间戳，仅在确定边界时转换为北京时间
    
    **示例** (北京时间):
    1. day=1 (今天北京0点到现在)
       - 输入: 2026-01-26 00:00:00+08:00 ~ 2026-01-26 12:34:56+08:00
       - 输出: [不完整天: 00:00 ~ 12:34:56]
    
    2. day=2 (昨天+今天)
       - 输出:
         [完整天: 01-25 00:00+08:00 ~ 01-25 23:59:59+08:00]
         [不完整天: 01-26 00:00+08:00 ~ 01-26 12:34:56+08:00]
    
    Args:
        start_time: 开始时间（UTC）
        end_time: 结束时间（UTC）
        
    Returns:
        时间切片列表（时间戳为 UTC）
    """
    slices = []
    
    # 1. 将 start/end 转换为北京时间，确定北京日期边界
    start_bj = to_beijing(start_time)
    end_bj = to_beijing(end_time)
    
    # 2. 北京时间当天 0:00 作为起始日期
    current_date_bj = start_bj.replace(hour=0, minute=0, second=0, microsecond=0)
    day_index = 1
    
    while current_date_bj < end_bj:
        # 当天北京 0:00 和次日北京 0:00（转换为 UTC 用于边界比较）
        day_start_utc = current_date_bj.astimezone(timezone.utc)
        next_day_start_utc = (current_date_bj + timedelta(days=1)).astimezone(timezone.utc)
        
        # 实际边界：取 max/min 裁剪
        actual_start = max(day_start_utc, start_time)
        actual_end = min(
            next_day_start_utc - timedelta(seconds=1),
            end_time
        )
        
        # 判断是否为完整天
        is_full = _is_full_day(actual_start, actual_end, day_start_utc)
        
        # 日期标签使用北京日期
        date_label = current_date_bj.strftime("%Y-%m-%d")
        
        slice_obj = TimeSlice(
            start_time=actual_start,
            end_time=actual_end,
            date=date_label,
            is_full_day=is_full,
            day_index=day_index
        )
        slices.append(slice_obj)
        
        # 移动到下一个北京日
        current_date_bj += timedelta(days=1)
        day_index += 1
    
    return slices


def _is_full_day(
    actual_start: datetime,
    actual_end: datetime,
    day_boundary: datetime
) -> bool:
    """判断是否为完整天
    
    Args:
        actual_start: 实际开始时间 (UTC)
        actual_end: 实际结束时间 (UTC)
        day_boundary: 北京当天0点对应的 UTC 时间
        
    Returns:
        是否为完整天（北京 0:00:00 ~ 23:59:59）
    """
    expected_start = day_boundary
    expected_end = day_boundary + timedelta(days=1) - timedelta(seconds=1)
    
    # 允许1秒的误差
    start_match = abs((actual_start - expected_start).total_seconds()) <= 1
    end_match = abs((actual_end - expected_end).total_seconds()) <= 1
    
    return start_match and end_match


def get_day_boundaries(date: datetime) -> Tuple[datetime, datetime]:
    """获取某天的北京时间边界
    
    Args:
        date: 任意时间点 (UTC 或带时区)
        
    Returns:
        (当天北京0点的UTC时间, 当天北京23:59:59的UTC时间)
    """
    date_bj = to_beijing(date)
    day_start_bj = date_bj.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end_bj = day_start_bj + timedelta(days=1) - timedelta(seconds=1)
    return day_start_bj.astimezone(timezone.utc), day_end_bj.astimezone(timezone.utc)


def parse_days_parameter(days: int) -> Tuple[datetime, datetime]:
    """解析 days 参数为时间范围（北京时间自然日）
    
    **逻辑** (以北京时间为基准):
    - day=1: 今天北京0点到现在
    - day=2: 昨天北京0点到现在
    - day=N: N-1天前北京0点到现在
    
    Args:
        days: 天数（从1开始）
        
    Returns:
        (start_time, end_time) —— 均为 UTC
    """
    from app.tools.timezone_tools import now_beijing
    
    now_bj = now_beijing()
    end_time = now_bj.astimezone(timezone.utc)
    
    # 从北京时间今天0点往前推 N-1 天
    today_midnight_bj = now_bj.replace(hour=0, minute=0, second=0, microsecond=0)
    start_time_bj = today_midnight_bj - timedelta(days=days - 1)
    start_time = start_time_bj.astimezone(timezone.utc)
    
    return start_time, end_time


def format_time_slices_summary(slices: List[TimeSlice]) -> str:
    """格式化时间切片摘要（用于日志）
    
    Args:
        slices: 时间切片列表
        
    Returns:
        摘要字符串
    """
    lines = [f"时间切片: {len(slices)} 天"]
    for s in slices:
        status = "[完整天]" if s.is_full_day else "[不完整天]"
        lines.append(f"  Day {s.day_index}: {s.date} {status}")
    return "\n".join(lines)


# ============================================================
# 测试代码
# ============================================================
if __name__ == "__main__":
    print("=" * 70)
    print("时间切片工具测试 (北京时间边界)")
    print("=" * 70)
    
    # 测试1: day=1 (今天北京0点到现在)
    print("\n[测试1] day=1 (今天北京0点到现在)")
    start1, end1 = parse_days_parameter(1)
    slices1 = split_time_range_by_natural_days(start1, end1)
    print(format_time_slices_summary(slices1))
    
    # 测试2: day=2 (昨天+今天)
    print("\n[测试2] day=2 (昨天+今天)")
    start2, end2 = parse_days_parameter(2)
    slices2 = split_time_range_by_natural_days(start2, end2)
    print(format_time_slices_summary(slices2))
    
    # 测试3: 跨天查询 (前天10点到今天10点, 北京时间)
    print("\n[测试3] 跨天查询 (前天北京10点到今天北京10点)")
    now_bj = datetime.now(BEIJING_TZ)
    start3_bj = (now_bj - timedelta(days=2)).replace(hour=10, minute=0, second=0, microsecond=0)
    end3_bj = now_bj.replace(hour=10, minute=0, second=0, microsecond=0)
    slices3 = split_time_range_by_natural_days(
        start3_bj.astimezone(timezone.utc),
        end3_bj.astimezone(timezone.utc)
    )
    print(format_time_slices_summary(slices3))
