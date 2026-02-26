# ============================================================
# 文件说明: alarm_store.py - 报警记录存储（InfluxDB + 去重）
# ============================================================
# 方法列表:
# 1. log_alarm()      - 记录报警事件（60秒去重）
# 2. query_alarms()   - 查询历史报警记录
# 3. get_alarm_count()- 统计报警数量
# ============================================================
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

from app.core.influxdb import get_influx_client, write_point
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_MEASUREMENT = "alarm_logs"

# 60秒内同一参数同一级别不重复写入
_ALARM_DEDUP_SECONDS = 60
_last_alarms: Dict[str, datetime] = {}


# ------------------------------------------------------------
# 1. log_alarm() - 记录报警事件（60秒去重）
# ------------------------------------------------------------
def log_alarm(
    device_id: str,
    alarm_type: str,
    param_name: str,
    value: float,
    threshold: float,
    level: str,
    message: str,
    timestamp: Optional[datetime] = None,
) -> bool:
    """
    写入一条报警记录到 InfluxDB。60 秒内同一 dedup_key 只写一次。
    返回 True 表示实际写入，False 表示被去重跳过。
    """
    dedup_key = f"{device_id}_{param_name}_{level}"
    now = datetime.now(timezone.utc)
    last = _last_alarms.get(dedup_key)
    if last is not None:
        delta = (now - last).total_seconds()
        if delta < _ALARM_DEDUP_SECONDS:
            return False

    _last_alarms[dedup_key] = now

    ts = timestamp if timestamp is not None else now

    tags = {
        "device_id": device_id,
        "alarm_type": alarm_type,
        "level": level,
    }
    fields = {
        "param_name": param_name,
        "value": float(value),
        "threshold": float(threshold),
        "message": message,
    }

    # [注意] fields 中包含字符串，write_point 会跳过字符串字段
    # 单独处理字符串字段 param_name / message -> 写为 tag
    tags["param_name"] = param_name

    numeric_fields = {
        "value": float(value),
        "threshold": float(threshold),
    }

    try:
        ok = write_point(_MEASUREMENT, tags, numeric_fields, ts)
        if ok:
            logger.warning(
                "[Alarm] %s | device=%s | %s=%.2f > %.2f",
                level.upper(), device_id, param_name, value, threshold,
            )
        return ok
    except Exception as e:
        logger.error("[Alarm] 写入报警记录失败: %s", e, exc_info=True)
        return False


# ------------------------------------------------------------
# 2. query_alarms() - 查询历史报警记录
# ------------------------------------------------------------
def query_alarms(
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    level: Optional[str] = None,
    param_prefix: Optional[str] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """
    查询报警记录列表。
    param_prefix: 按 param_name 前缀过滤 (如 "rotary_temp", "scr_power_1")
    返回按时间倒序的报警记录，每条包含 time/device_id/param_name/level/value/threshold。
    """
    now = datetime.now(timezone.utc)
    if start_time is None:
        start_time = now - timedelta(hours=24)
    if end_time is None:
        end_time = now

    # 确保时区 UTC
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)

    level_filter = f'  |> filter(fn: (r) => r["level"] == "{level}")' if level else ""
    prefix_filter = ""
    if param_prefix:
        safe = param_prefix.replace(".", r"\.").replace("(", r"\(").replace(")", r"\)")
        prefix_filter = f'  |> filter(fn: (r) => r["param_name"] =~ /^{safe}/)'

    query = f'''
from(bucket: "{settings.influx_bucket}")
  |> range(start: {start_time.isoformat()}, stop: {end_time.isoformat()})
  |> filter(fn: (r) => r["_measurement"] == "{_MEASUREMENT}")
{level_filter}
{prefix_filter}
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> sort(columns: ["_time"], desc: true)
  |> limit(n: {limit})
'''

    try:
        client = get_influx_client()
        q_api = client.query_api()
        tables = q_api.query(query)
        results = []
        for table in tables:
            for record in table.records:
                results.append({
                    "time": record.get_time().isoformat(),
                    "device_id": record.values.get("device_id", ""),
                    "alarm_type": record.values.get("alarm_type", ""),
                    "param_name": record.values.get("param_name", ""),
                    "level": record.values.get("level", ""),
                    "value": record.values.get("value"),
                    "threshold": record.values.get("threshold"),
                })
        return results
    except Exception as e:
        logger.error("[Alarm] 查询报警记录失败: %s", e, exc_info=True)
        return []


# ------------------------------------------------------------
# 3. get_alarm_count() - 统计报警数量
# ------------------------------------------------------------
def get_alarm_count(hours: int = 24) -> Dict[str, int]:
    """
    统计指定时长内的各级别报警数量。
    返回: {"warning": N, "alarm": N, "total": N}
    """
    now = datetime.now(timezone.utc)
    start_time = now - timedelta(hours=hours)

    query = f'''
from(bucket: "{settings.influx_bucket}")
  |> range(start: {start_time.isoformat()}, stop: {now.isoformat()})
  |> filter(fn: (r) => r["_measurement"] == "{_MEASUREMENT}")
  |> filter(fn: (r) => r["_field"] == "value")
  |> group(columns: ["level"])
  |> count()
'''

    try:
        client = get_influx_client()
        q_api = client.query_api()
        tables = q_api.query(query)
        counts: Dict[str, int] = {"warning": 0, "alarm": 0, "total": 0}
        for table in tables:
            for record in table.records:
                lv = record.values.get("level", "")
                cnt = int(record.get_value() or 0)
                if lv in counts:
                    counts[lv] = cnt
                    counts["total"] += cnt
        return counts
    except Exception as e:
        logger.error("[Alarm] 统计报警数量失败: %s", e, exc_info=True)
        return {"warning": 0, "alarm": 0, "total": 0}
