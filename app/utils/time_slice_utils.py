# ============================================================
# 文件说明: time_slice_utils.py - 时间切片工具
# ============================================================
# 功能:
# 1. 按自然日切分时间段（0:00-23:59）
# 2. 区分完整天和不完整天
# 3. 支持跨天查询的智能切片
# ============================================================
# 方法列表:
# 1. split_time_range_by_natural_days()  - 按自然日切分时间段
# 2. is_full_day()                       - 判断是否为完整天
# 3. get_day_boundaries()                - 获取某天的边界时间
# ============================================================

from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Tuple


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
    """按自然日切分时间段
    
    **核心逻辑**:
    - 完整天: 0:00:00 ~ 23:59:59
    - 不完整天: 实际时间段
    
    **示例**:
    1. day=1 (今天0点到现在)
       - 输入: 2026-01-26 00:00:00 ~ 2026-01-26 12:34:56
       - 输出: [不完整天: 2026-01-26 00:00:00 ~ 2026-01-26 12:34:56]
    
    2. day=2 (昨天+今天)
       - 输入: 2026-01-25 00:00:00 ~ 2026-01-26 12:34:56
       - 输出: 
         [完整天: 2026-01-25 00:00:00 ~ 2026-01-25 23:59:59]
         [不完整天: 2026-01-26 00:00:00 ~ 2026-01-26 12:34:56]
    
    3. 跨天查询 (前天10点到今天10点)
       - 输入: 2026-01-24 10:00:00 ~ 2026-01-26 10:00:00
       - 输出:
         [不完整天: 2026-01-24 10:00:00 ~ 2026-01-24 23:59:59]
         [完整天: 2026-01-25 00:00:00 ~ 2026-01-25 23:59:59]
         [不完整天: 2026-01-26 00:00:00 ~ 2026-01-26 10:00:00]
    
    Args:
        start_time: 开始时间（UTC）
        end_time: 结束时间（UTC）
        
    Returns:
        时间切片列表
    """
    slices = []
    current_date = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
    day_index = 1
    
    while current_date < end_time:
        # 计算当天的边界
        day_start = max(current_date, start_time)
        day_end = min(
            current_date + timedelta(days=1) - timedelta(seconds=1),
            end_time
        )
        
        # 判断是否为完整天
        is_full = _is_full_day(day_start, day_end, current_date)
        
        # 创建切片
        slice_obj = TimeSlice(
            start_time=day_start,
            end_time=day_end,
            date=current_date.strftime("%Y-%m-%d"),
            is_full_day=is_full,
            day_index=day_index
        )
        slices.append(slice_obj)
        
        # 移动到下一天
        current_date += timedelta(days=1)
        day_index += 1
    
    return slices


def _is_full_day(
    actual_start: datetime,
    actual_end: datetime,
    day_boundary: datetime
) -> bool:
    """判断是否为完整天
    
    Args:
        actual_start: 实际开始时间
        actual_end: 实际结束时间
        day_boundary: 当天0点
        
    Returns:
        是否为完整天（0:00:00 ~ 23:59:59）
    """
    expected_start = day_boundary
    expected_end = day_boundary + timedelta(days=1) - timedelta(seconds=1)
    
    # 允许1秒的误差
    start_match = abs((actual_start - expected_start).total_seconds()) <= 1
    end_match = abs((actual_end - expected_end).total_seconds()) <= 1
    
    return start_match and end_match


def get_day_boundaries(date: datetime) -> Tuple[datetime, datetime]:
    """获取某天的边界时间
    
    Args:
        date: 任意时间点
        
    Returns:
        (当天0点, 当天23:59:59)
    """
    day_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1) - timedelta(seconds=1)
    return day_start, day_end


def parse_days_parameter(days: int) -> Tuple[datetime, datetime]:
    """解析 days 参数为时间范围
    
    **逻辑**:
    - day=1: 今天0点到现在
    - day=2: 昨天0点到今天现在
    - day=N: N-1天前0点到今天现在
    
    Args:
        days: 天数（从1开始）
        
    Returns:
        (start_time, end_time)
    """
    now = datetime.now(timezone.utc)
    end_time = now
    
    # 计算开始时间：N-1天前的0点
    start_time = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
    
    return start_time, end_time


def format_time_slices_summary(slices: List[TimeSlice]) -> str:
    """格式化时间切片摘要（用于日志）
    
    Args:
        slices: 时间切片列表
        
    Returns:
        摘要字符串
    """
    lines = [f"📅 时间切片: {len(slices)} 天"]
    for s in slices:
        status = "✅完整天" if s.is_full_day else "⚠️不完整天"
        lines.append(f"  Day {s.day_index}: {s.date} {status}")
    return "\n".join(lines)


# ============================================================
# 测试代码
# ============================================================
if __name__ == "__main__":
    print("=" * 70)
    print("时间切片工具测试")
    print("=" * 70)
    
    # 测试1: day=1 (今天0点到现在)
    print("\n【测试1】day=1 (今天0点到现在)")
    start1, end1 = parse_days_parameter(1)
    slices1 = split_time_range_by_natural_days(start1, end1)
    print(format_time_slices_summary(slices1))
    
    # 测试2: day=2 (昨天+今天)
    print("\n【测试2】day=2 (昨天+今天)")
    start2, end2 = parse_days_parameter(2)
    slices2 = split_time_range_by_natural_days(start2, end2)
    print(format_time_slices_summary(slices2))
    
    # 测试3: 跨天查询 (前天10点到今天10点)
    print("\n【测试3】跨天查询 (前天10点到今天10点)")
    now = datetime.now(timezone.utc)
    start3 = now - timedelta(days=2, hours=-10)  # 前天10点
    end3 = now.replace(hour=10, minute=0, second=0, microsecond=0)  # 今天10点
    slices3 = split_time_range_by_natural_days(start3, end3)
    print(format_time_slices_summary(slices3))

