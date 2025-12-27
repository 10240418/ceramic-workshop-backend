# ============================================================
# 文件说明: influxdb.py - InfluxDB 客户端管理
# ============================================================
# 方法列表:
# 1. get_influx_client()    - 获取InfluxDB客户端
# 2. check_influx_health()  - 检查InfluxDB健康状态
# 3. write_point()          - 写入单个数据点
# 4. write_points()         - 批量写入数据点
# 5. write_points_batch()   - 批量写入（带返回值）
# 6. build_point()          - 构建Point对象
# 7. query_data()           - 查询历史数据
# ============================================================

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone
from functools import lru_cache
import threading

from config import get_settings

settings = get_settings()

# 写入锁（防止并发写入问题）
_write_lock = threading.Lock()


# ------------------------------------------------------------
# 1. get_influx_client() - 获取InfluxDB客户端
# ------------------------------------------------------------
@lru_cache()
def get_influx_client() -> InfluxDBClient:
    """获取InfluxDB客户端单例"""
    return InfluxDBClient(
        url=settings.influx_url,
        token=settings.influx_token,
        org=settings.influx_org
    )


# ------------------------------------------------------------
# 2. check_influx_health() - 检查InfluxDB健康状态
# ------------------------------------------------------------
def check_influx_health() -> Tuple[bool, str]:
    """
    检查 InfluxDB 连接健康状态
    
    Returns:
        (healthy, message)
    """
    try:
        client = get_influx_client()
        health = client.health()
        if health.status == "pass":
            return (True, "InfluxDB 正常")
        return (False, f"InfluxDB 状态: {health.status}")
    except Exception as e:
        return (False, str(e))


# ------------------------------------------------------------
# 3. write_point() - 写入单个数据点
# ------------------------------------------------------------
def write_point(measurement: str, tags: Dict[str, str], fields: Dict[str, Any], timestamp: Optional[datetime] = None) -> bool:
    """写入单个数据点到InfluxDB
    
    Returns:
        写入是否成功
    """
    try:
        client = get_influx_client()
        write_api = client.write_api(write_options=SYNCHRONOUS)
        
        point = _build_point(measurement, tags, fields, timestamp)
        if point is None:
            return False
        
        with _write_lock:
            write_api.write(bucket=settings.influx_bucket, org=settings.influx_org, record=point)
        return True
    except Exception as e:
        print(f"❌ InfluxDB 写入失败: {e}")
        return False


# ------------------------------------------------------------
# 4. write_points() - 批量写入数据点
# ------------------------------------------------------------
def write_points(points: List[Point]):
    """批量写入数据点到InfluxDB"""
    if not points:
        return
    client = get_influx_client()
    write_api = client.write_api(write_options=SYNCHRONOUS)
    with _write_lock:
        write_api.write(bucket=settings.influx_bucket, org=settings.influx_org, record=points)


# ------------------------------------------------------------
# 5. write_points_batch() - 批量写入（带返回值）
# ------------------------------------------------------------
def write_points_batch(points: List[Point]) -> Tuple[bool, str]:
    """
    批量写入数据点到 InfluxDB
    
    Args:
        points: Point 对象列表
    
    Returns:
        (success, error_message)
    """
    if not points:
        return (True, "")
    
    try:
        client = get_influx_client()
        write_api = client.write_api(write_options=SYNCHRONOUS)
        
        with _write_lock:
            write_api.write(bucket=settings.influx_bucket, org=settings.influx_org, record=points)
        
        return (True, "")
    except Exception as e:
        return (False, str(e))


# ------------------------------------------------------------
# 6. build_point() - 构建Point对象
# ------------------------------------------------------------
def build_point(measurement: str, tags: Dict[str, str], fields: Dict[str, Any], timestamp: Optional[datetime] = None) -> Optional[Point]:
    """
    构建 InfluxDB Point 对象（供外部批量使用）
    
    Returns:
        Point 对象或 None (如果字段为空)
    """
    return _build_point(measurement, tags, fields, timestamp)


def _build_point(measurement: str, tags: Dict[str, str], fields: Dict[str, Any], timestamp: Optional[datetime] = None) -> Optional[Point]:
    """内部方法：构建 Point 对象"""
    point = Point(measurement)
    
    for k, v in tags.items():
        point = point.tag(k, v)
    
    valid_fields = 0
    for k, v in fields.items():
        # 跳过 None 值
        if v is None:
            continue
        # InfluxDB 不支持存储字符串作为 field (会导致类型冲突)
        if isinstance(v, str):
            continue
        point = point.field(k, v)
        valid_fields += 1
    
    if valid_fields == 0:
        return None
    
    # 确保时间戳带时区信息 (UTC)
    if timestamp:
        if timestamp.tzinfo is None:
            # 本地时间转UTC
            timestamp = timestamp.astimezone(timezone.utc)
        point = point.time(timestamp)
    
    return point


# ------------------------------------------------------------
# 7. query_data() - 查询历史数据
# ------------------------------------------------------------
def query_data(
    measurement: str,
    start_time: datetime,
    end_time: datetime,
    tags: Optional[Dict[str, str]] = None,
    interval: str = "1m"
) -> List[Dict[str, Any]]:
    """
    查询InfluxDB历史数据
    
    Args:
        measurement: 测量名称
        start_time: 开始时间
        end_time: 结束时间
        tags: 标签过滤条件
        interval: 聚合间隔
    
    Returns:
        查询结果列表
    """
    client = get_influx_client()
    query_api = client.query_api()
    
    # 构建Flux查询
    tag_filter = ""
    if tags:
        tag_conditions = [f'r["{k}"] == "{v}"' for k, v in tags.items()]
        tag_filter = " and ".join(tag_conditions)
        tag_filter = f" |> filter(fn: (r) => {tag_filter})"
    
    query = f'''
    from(bucket: "{settings.influx_bucket}")
        |> range(start: {start_time.isoformat()}Z, stop: {end_time.isoformat()}Z)
        |> filter(fn: (r) => r["_measurement"] == "{measurement}")
        {tag_filter}
        |> aggregateWindow(every: {interval}, fn: mean, createEmpty: false)
        |> yield(name: "mean")
    '''
    
    result = query_api.query(query)
    
    # 解析结果
    data = []
    for table in result:
        for record in table.records:
            data.append({
                "time": record.get_time(),
                "field": record.get_field(),
                "value": record.get_value(),
                **{k: v for k, v in record.values.items() if k.startswith("_") is False}
            })
    
    return data
