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
from influxdb_client.client.write_api import SYNCHRONOUS, WriteApi
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone
import threading

from config import get_settings

settings = get_settings()

# 1, 写入锁 - 防止并发写入导致数据竞争
_write_lock = threading.Lock()

# 2, 全局客户端实例 - 单例模式复用连接
_influx_client: Optional[InfluxDBClient] = None

# 3, 全局写入 API - 避免每次写入创建新实例 (修复资源泄漏)
_write_api: Optional[WriteApi] = None


# ------------------------------------------------------------
# 1. get_influx_client() - 获取InfluxDB客户端
# ------------------------------------------------------------
def get_influx_client() -> InfluxDBClient:
    """获取 InfluxDB 客户端单例
    
    # 2, 使用单例模式复用连接，避免连接池耗尽
    """
    global _influx_client
    if _influx_client is None:
        _influx_client = InfluxDBClient(
            url=settings.influx_url,
            token=settings.influx_token,
            org=settings.influx_org,
            enable_gzip=True,
            timeout=30_000,  # 30秒超时
        )
    return _influx_client


def _get_write_api() -> WriteApi:
    """获取写入 API 单例
    
    # 3, 复用 write_api 实例，避免资源泄漏
    """
    global _write_api
    if _write_api is None:
        _write_api = get_influx_client().write_api(write_options=SYNCHRONOUS)
    return _write_api


def close_influx_client() -> None:
    """关闭 InfluxDB 客户端（应用退出时调用）
    
    # 3, 先关闭 write_api
    # 2, 再关闭 client
    """
    global _influx_client, _write_api
    
    # 3, 先关闭 write_api
    if _write_api is not None:
        try:
            _write_api.close()
        except Exception as e:
            print(f"⚠️ 关闭 write_api 失败: {e}")
        finally:
            _write_api = None
    
    # 2, 再关闭 client
    if _influx_client is not None:
        try:
            _influx_client.close()
            print("✅ InfluxDB 客户端已关闭")
        except Exception as e:
            print(f"⚠️ 关闭 InfluxDB 客户端失败: {e}")
        finally:
            _influx_client = None


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
    """写入单个数据点到 InfluxDB
    
    # 1, 使用写入锁保证线程安全
    # 3, 使用单例 write_api 避免资源泄漏
    
    Returns:
        写入是否成功
    """
    point = _build_point(measurement, tags, fields, timestamp)
    if point is None:
        return False
    
    try:
        # 1, 使用写入锁保证线程安全
        with _write_lock:
            # 3, 使用单例 write_api
            _get_write_api().write(
                bucket=settings.influx_bucket,
                org=settings.influx_org,
                record=point
            )
        return True
    except Exception as e:
        print(f"❌ InfluxDB 写入失败: {e}")
        return False


# ------------------------------------------------------------
# 4. write_points() - 批量写入数据点
# ------------------------------------------------------------
def write_points(points: List[Point]) -> None:
    """批量写入数据点到 InfluxDB (无返回值版本，建议使用 write_points_batch)
    
    # 3, 使用单例 write_api 避免资源泄漏
    """
    if not points:
        return
    # 1, 使用写入锁保证线程安全
    with _write_lock:
        # 3, 使用单例 write_api
        _get_write_api().write(
            bucket=settings.influx_bucket,
            org=settings.influx_org,
            record=points
        )


# ------------------------------------------------------------
# 5. write_points_batch() - 批量写入（带返回值）
# ------------------------------------------------------------
def write_points_batch(points: List[Point]) -> Tuple[bool, str]:
    """批量写入数据点到 InfluxDB
    
    # 1, 使用写入锁保证线程安全
    # 3, 使用单例 write_api 避免资源泄漏
    
    Args:
        points: Point 对象列表
    
    Returns:
        (success, error_message)
    """
    if not points:
        return (True, "")
    
    try:
        # 1, 使用写入锁保证线程安全
        with _write_lock:
            # 3, 使用单例 write_api
            _get_write_api().write(
                bucket=settings.influx_bucket,
                org=settings.influx_org,
                record=points
            )
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
    """内部方法：构建 Point 对象
    
    # 4, 跳过 None 值和字符串字段 (InfluxDB 类型冲突)
    # 5, 确保时间戳带 UTC 时区
    """
    point = Point(measurement)
    
    for k, v in tags.items():
        point = point.tag(k, v)
    
    valid_fields = 0
    for k, v in fields.items():
        # 4, 跳过无效字段
        if v is None or isinstance(v, str):
            continue
        point = point.field(k, v)
        valid_fields += 1
    
    if valid_fields == 0:
        return None
    
    # 5, 时间戳处理: 无时区信息时假设为 UTC (修复原来的 astimezone 错误)
    if timestamp:
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        else:
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
    """查询 InfluxDB 历史数据
    
    # 6, Flux 查询构建
    # 7, 结果解析
    
    Args:
        measurement: 测量名称
        start_time: 开始时间
        end_time: 结束时间
        tags: 标签过滤条件
        interval: 聚合间隔
    
    Returns:
        查询结果列表
    """
    try:
        client = get_influx_client()
        query_api = client.query_api()
        
        # 6, 构建 Flux 查询
        tag_filter = ""
        if tags:
            tag_conditions = [f'r["{k}"] == "{v}"' for k, v in tags.items()]
            tag_filter = f" |> filter(fn: (r) => {' and '.join(tag_conditions)})"
        
        query = f'''
        from(bucket: "{settings.influx_bucket}")
            |> range(start: {start_time.isoformat()}Z, stop: {end_time.isoformat()}Z)
            |> filter(fn: (r) => r["_measurement"] == "{measurement}")
            {tag_filter}
            |> aggregateWindow(every: {interval}, fn: mean, createEmpty: false)
            |> yield(name: "mean")
        '''
        
        result = query_api.query(query)
        
        # 7, 解析结果
        data = []
        for table in result:
            for record in table.records:
                data.append({
                    "time": record.get_time(),
                    "field": record.get_field(),
                    "value": record.get_value(),
                    **{k: v for k, v in record.values.items() if not k.startswith("_")}
                })
        
        return data
    except Exception as e:
        print(f"❌ InfluxDB 查询失败: {e}")
        return []
