# ============================================================
# 文件说明: alarm.py - 报警管理路由
# ============================================================
# 接口列表:
# 1. GET  /api/alarm/thresholds  - 获取全量阈值配置
# 2. PUT  /api/alarm/thresholds  - 更新阈值配置（前端同步）
# 3. GET  /api/alarm/records     - 查询历史报警记录
# 4. GET  /api/alarm/count       - 统计报警数量
# ============================================================
from fastapi import APIRouter, Query
from datetime import datetime
from typing import Optional
import logging

from app.models.response import ApiResponse
from app.alarm_thresholds import AlarmThresholdManager

logger = logging.getLogger(__name__)
from app.core.alarm_store import query_alarms, get_alarm_count

router = APIRouter(prefix="/api/alarm", tags=["报警"])


# ------------------------------------------------------------
# 1. GET /api/alarm/thresholds - 获取全量阈值配置
# ------------------------------------------------------------
@router.get("/thresholds")
async def get_thresholds():
    """获取全量报警阈值配置（30个参数）"""
    try:
        manager = AlarmThresholdManager.get_instance()
        return ApiResponse.ok(manager.get_all())
    except Exception as e:
        logger.error("[Alarm] get thresholds failed: %s", e, exc_info=True)
        return ApiResponse.fail(str(e))


# ------------------------------------------------------------
# 2. PUT /api/alarm/thresholds - 更新阈值配置
# ------------------------------------------------------------
@router.put("/thresholds")
async def update_thresholds(body: dict):
    """
    接收前端推送的阈值字典，格式:
    {
      "rotary_temp_short_hopper_1": {"warning_max": 900.0, "alarm_max": 1100.0, "enabled": true},
      ...
    }
    """
    try:
        manager = AlarmThresholdManager.get_instance()
        ok = manager.save(body)
        if ok:
            return ApiResponse.ok({"updated": len(body), "message": "阈值配置已保存"})
        return ApiResponse.fail("保存阈值配置失败")
    except Exception as e:
        logger.error("[Alarm] update thresholds failed: %s", e, exc_info=True)
        return ApiResponse.fail(str(e))


# ------------------------------------------------------------
# 3. GET /api/alarm/records - 查询历史报警记录
# ------------------------------------------------------------
@router.get("/records")
async def get_alarm_records(
    start: Optional[str] = Query(None, description="开始时间 ISO8601，如 2026-01-01T00:00:00Z"),
    end: Optional[str] = Query(None, description="结束时间 ISO8601"),
    level: Optional[str] = Query(None, description="报警级别: warning | alarm"),
    param_prefix: Optional[str] = Query(None, description="参数名前缀过滤，如 rotary_temp, scr_power_1"),
    limit: int = Query(200, ge=1, le=1000, description="返回条数上限"),
):
    """查询历史报警记录，默认返回最近24小时"""
    try:
        start_dt: Optional[datetime] = None
        end_dt: Optional[datetime] = None
        if start:
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        if end:
            end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))

        records = query_alarms(
            start_time=start_dt,
            end_time=end_dt,
            level=level,
            param_prefix=param_prefix,
            limit=limit,
        )
        return ApiResponse.ok({"records": records, "count": len(records)})
    except Exception as e:
        logger.error("[Alarm] query alarm records failed: %s", e, exc_info=True)
        return ApiResponse.fail(str(e))


# ------------------------------------------------------------
# 4. GET /api/alarm/count - 统计报警数量
# ------------------------------------------------------------
@router.get("/count")
async def get_count(
    hours: int = Query(24, ge=1, le=168, description="统计时长（小时），最长7天"),
):
    """统计指定时长内的各级别报警数量"""
    try:
        counts = get_alarm_count(hours=hours)
        return ApiResponse.ok(counts)
    except Exception as e:
        logger.error("[Alarm] get alarm count failed: %s", e, exc_info=True)
        return ApiResponse.fail(str(e))
