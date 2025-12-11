# ============================================================
# 文件说明: influxdb.py - InfluxDB 客户端管理
# ============================================================
# 方法列表:
# 1. get_influx_client()    - 获取InfluxDB客户端
# 2. write_point()          - 写入单个数据点
# 3. write_points()         - 批量写入数据点
# 4. query_data()           - 查询历史数据
# ============================================================

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from functools import lru_cache

from config import get_settings

settings = get_settings()


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
# 2. write_point() - 写入单个数据点
# ------------------------------------------------------------
def write_point(measurement: str, tags: Dict[str, str], fields: Dict[str, Any], timestamp: Optional[datetime] = None):
    """写入单个数据点到InfluxDB"""
    client = get_influx_client()
    write_api = client.write_api(write_options=SYNCHRONOUS)
    
    point = Point(measurement)
    for key, value in tags.items():
        point = point.tag(key, value)
    for key, value in fields.items():
        point = point.field(key, value)
    
    # 确保时间戳带时区信息 (UTC)
    if timestamp:
        if timestamp.tzinfo is None:
            # 本地时间转UTC
            timestamp = timestamp.astimezone(timezone.utc)
        point = point.time(timestamp)
    
    write_api.write(bucket=settings.influx_bucket, org=settings.influx_org, record=point)


# ------------------------------------------------------------
# 3. write_points() - 批量写入数据点
# ------------------------------------------------------------
def write_points(points: List[Point]):
    """批量写入数据点到InfluxDB"""
    if not points:
        return
    client = get_influx_client()
    write_api = client.write_api(write_options=SYNCHRONOUS)
    write_api.write(bucket=settings.influx_bucket, org=settings.influx_org, record=points)


# ------------------------------------------------------------
# 4. query_data() - 查询历史数据
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
