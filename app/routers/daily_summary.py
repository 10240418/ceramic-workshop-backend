# ============================================================
# 文件说明: daily_summary.py - 日汇总数据管理API
# ============================================================
# 接口列表:
# 1. POST /api/daily-summary/calculate        - 手动计算指定日期的汇总数据
# 2. POST /api/daily-summary/fill-missing     - 检测并补全缺失日期
# 3. GET  /api/daily-summary/available-dates  - 获取已有的日期列表
# 4. GET  /api/daily-summary/query            - 查询日汇总数据
# 5. GET  /api/daily-summary/recalculate      - 强制重算指定日期范围
# 6. GET  /api/daily-summary/runtime-inspect  - 诊断: 查看全部设备运行时长数据
# ============================================================

from fastapi import APIRouter, Query
from datetime import datetime, timedelta, timezone
from typing import Optional
import asyncio
import logging

from app.tools.timezone_tools import BEIJING_TZ
from app.models.response import ApiResponse
from app.services.daily_summary_service import get_daily_summary_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/daily-summary", tags=["日汇总数据管理"])


# ============================================================
# 1. POST /api/daily-summary/calculate - 手动计算日汇总
# ============================================================
@router.post("/calculate")
def calculate_daily_summary(
    target_date: Optional[str] = Query(None, description="目标日期 (YYYY-MM-DD)，默认为昨天")
):
    """手动计算并存储指定日期的汇总数据
    
    **功能说明**:
    - 计算指定日期的所有设备数据汇总
    - 存储到 daily_summary measurement
    - 用于手动补全历史数据或修复错误数据
    
    **参数**:
    - target_date: 目标日期（YYYY-MM-DD格式）
    - 默认为昨天（因为今天的数据还不完整）
    
    **返回结构**:
    ```json
    {
        "success": true,
        "data": {
            "date": "2026-01-26",
            "success": true,
            "devices_processed": 20,
            "points_written": 80
        }
    }
    ```
    
    **示例**:
    ```
    # 计算昨天的汇总数据
    POST /api/daily-summary/calculate
    
    # 计算指定日期的汇总数据
    POST /api/daily-summary/calculate?target_date=2026-01-26
    ```
    """
    try:
        # 解析目标日期
        if target_date:
            target_dt = datetime.strptime(target_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            # 默认为昨天
            target_dt = datetime.now(timezone.utc) - timedelta(days=1)
        
        # 调用服务计算并存储
        service = get_daily_summary_service()
        result = service.calculate_and_store_daily_summary(target_dt)
        
        return ApiResponse.ok(result)
    
    except ValueError as e:
        return ApiResponse.fail(f"参数错误: {str(e)}")
    except Exception as e:
        logger.error("[DailySummary] calculate failed: %s", e, exc_info=True)
        return ApiResponse.fail(f"计算失败: {str(e)}")


# ============================================================
# 2. POST /api/daily-summary/fill-missing - 补全缺失日期
# ============================================================
@router.post("/fill-missing")
def fill_missing_dates(
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)，默认为昨天")
):
    """检测并补全缺失的日期数据
    
    **功能说明**:
    - 自动检测数据库中缺失的日期
    - 批量计算并存储缺失日期的汇总数据
    - 适用于系统维护或数据修复
    
    **参数**:
    - end_date: 检查的结束日期（默认为昨天）
    - 检查范围：从最早的数据日期到 end_date
    
    **返回结构**:
    ```json
    {
        "success": true,
        "data": {
            "checked_range": "2026-01-01 ~ 2026-01-26",
            "existing_dates": ["20260102", "20260103", ...],
            "missing_dates": ["20260106"],
            "filled_dates": ["20260106"],
            "total_filled": 1
        }
    }
    ```
    
    **示例**:
    ```
    # 检测并补全到昨天
    POST /api/daily-summary/fill-missing
    
    # 检测并补全到指定日期
    POST /api/daily-summary/fill-missing?end_date=2026-01-26
    ```
    """
    try:
        # 解析结束日期
        if end_date:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            # 默认为昨天
            end_dt = datetime.now(timezone.utc) - timedelta(days=1)
        
        # 调用服务检测并补全
        service = get_daily_summary_service()
        result = service.check_and_fill_missing_dates(end_dt)
        
        return ApiResponse.ok(result)
    
    except ValueError as e:
        return ApiResponse.fail(f"参数错误: {str(e)}")
    except Exception as e:
        logger.error("[DailySummary] fill missing dates failed: %s", e, exc_info=True)
        return ApiResponse.fail(f"补全失败: {str(e)}")


# ============================================================
# 3. GET /api/daily-summary/available-dates - 获取已有日期
# ============================================================
@router.get("/available-dates")
def get_available_dates():
    """获取已有的日期列表
    
    **功能说明**:
    - 查询数据库中已存储的日汇总数据日期
    - 用于前端显示数据覆盖范围
    - 用于检测数据完整性
    
    **返回结构**:
    ```json
    {
        "success": true,
        "data": {
            "dates": ["20260102", "20260103", "20260104", ...],
            "total_count": 25,
            "earliest_date": "20260102",
            "latest_date": "20260126"
        }
    }
    ```
    
    **示例**:
    ```
    GET /api/daily-summary/available-dates
    ```
    """
    try:
        service = get_daily_summary_service()
        dates = service.get_available_dates()
        
        result = {
            "dates": dates,
            "total_count": len(dates),
            "earliest_date": dates[0] if dates else None,
            "latest_date": dates[-1] if dates else None
        }
        
        return ApiResponse.ok(result)
    
    except Exception as e:
        logger.error("[DailySummary] query available dates failed: %s", e, exc_info=True)
        return ApiResponse.fail(f"查询失败: {str(e)}")


# ============================================================
# 4. GET /api/daily-summary/query - 查询日汇总数据
# ============================================================
@router.get("/query")
def query_daily_summary(
    device_id: str = Query(..., description="设备ID"),
    metric_type: str = Query(..., description="指标类型 (electricity, gas, feeding, runtime)"),
    start_date: str = Query(..., description="开始日期 (YYYY-MM-DD)"),
    end_date: str = Query(..., description="结束日期 (YYYY-MM-DD)")
):
    """查询日汇总数据
    
    **功能说明**:
    - 查询指定设备、指标类型、时间范围的日汇总数据
    - 用于数据验证和调试
    
    **参数**:
    - device_id: 设备ID（如 short_hopper_1, zone1, scr_1）
    - metric_type: 指标类型
      - electricity: 电量
      - gas: 燃气
      - feeding: 投料
      - runtime: 运行时长
    - start_date: 开始日期（YYYY-MM-DD）
    - end_date: 结束日期（YYYY-MM-DD）
    
    **返回结构**:
    ```json
    {
        "success": true,
        "data": [
            {
                "date": "20260126",
                "start_reading": 1234.56,
                "end_reading": 1456.78,
                "consumption": 222.22,
                "runtime_hours": 18.5,
                "feeding_amount": 0.0,
                "gas_consumption": 0.0
            },
            ...
        ]
    }
    ```
    
    **示例**:
    ```
    # 查询料仓电量数据
    GET /api/daily-summary/query?device_id=short_hopper_1&metric_type=electricity&start_date=2026-01-01&end_date=2026-01-31
    
    # 查询SCR燃气数据
    GET /api/daily-summary/query?device_id=scr_1&metric_type=gas&start_date=2026-01-01&end_date=2026-01-31
    ```
    """
    try:
        # 解析日期 (使用北京时区, 日汇总 timestamp 基于北京自然日零点)
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=BEIJING_TZ)
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=BEIJING_TZ)
        
        # 调用服务查询
        service = get_daily_summary_service()
        records = service.get_daily_summary(
            device_id=device_id,
            metric_type=metric_type,
            start_date=start_dt,
            end_date=end_dt
        )
        
        return ApiResponse.ok(records)
    
    except ValueError as e:
        return ApiResponse.fail(f"参数错误: {str(e)}")
    except Exception as e:
        logger.error("[DailySummary] query daily summary failed: %s", e, exc_info=True)
        return ApiResponse.fail(f"查询失败: {str(e)}")


# ============================================================
# 5. GET  /api/daily-summary/recalculate - 强制重算指定日期范围
# ============================================================
@router.get("/recalculate")
def recalculate_daily_summary(
    start_date: str = Query(..., description="开始日期 (YYYY-MM-DD)"),
    end_date: str = Query(..., description="结束日期 (YYYY-MM-DD)"),
    polling_interval: Optional[float] = Query(
        None,
        description="轮询间隔(秒), 不传则使用配置值。历史6s数据传6.0, 当前5s数据传5.0"
    ),
):
    """强制重算指定日期范围的日汇总数据 (GET - 浏览器直接调用)

    **浏览器直接访问即可触发重算**:
    ```
    # 旧数据(6s间隔)重算:
    http://localhost:8080/api/daily-summary/recalculate?start_date=2026-01-01&end_date=2026-02-28&polling_interval=6.0

    # 新数据(5s间隔)重算:
    http://localhost:8080/api/daily-summary/recalculate?start_date=2026-03-01&end_date=2026-03-02&polling_interval=5.0

    # 使用配置默认值(5.0s)重算:
    http://localhost:8080/api/daily-summary/recalculate?start_date=2026-03-01&end_date=2026-03-02
    ```

    **注意**:
    - 该操作会删除再重写, 请确认日期范围正确
    - 计算耗时约 1~3 秒/天, 大范围重算请耐心等待
    - 最大支持 120 天, 超过请分批调用
    - end_date 不能超过昨天 (今天的数据还不完整)
    """
    try:
        # 1. 解析日期 (使用北京时区, 因为日汇总基于北京自然日)
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=BEIJING_TZ)
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=BEIJING_TZ)

        # 2. 安全检查: start_date 不能大于 end_date
        if start_dt > end_dt:
            return ApiResponse.fail(
                f"日期范围错误: start_date({start_date}) > end_date({end_date}), "
                f"请检查参数顺序"
            )

        # 3. 安全检查: end_date 不能超过昨天 (北京时间)
        yesterday = datetime.now(BEIJING_TZ).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=1)
        if end_dt > yesterday:
            end_dt = yesterday
            end_date = end_dt.strftime("%Y-%m-%d")
            logger.info("[DailySummary] end_date 修正为昨天: %s", end_date)

        # 4. 安全检查: 最大 120 天
        total_days = (end_dt - start_dt).days + 1
        if total_days > 120:
            return ApiResponse.fail(
                f"日期范围过大: {total_days}天, 最大支持120天。"
                f"请分批调用, 如先调用 1月, 再调用 2月"
            )

        service = get_daily_summary_service()
        result = service.force_recalculate_range(
            start_date=start_date,
            end_date=end_date,
            polling_interval=polling_interval,
        )
        return ApiResponse.ok(result)

    except ValueError as e:
        return ApiResponse.fail(f"参数错误: {str(e)}")
    except Exception as e:
        logger.error("[DailySummary] recalculate failed: %s", e, exc_info=True)
        return ApiResponse.fail(f"重算失败: {str(e)}")


# ============================================================
# 6. GET /runtime-inspect - 诊断: 查看全部设备运行时长数据
# ============================================================
@router.get("/runtime-inspect")
async def runtime_inspect(
    start_date: str = Query(..., description="开始日期 (YYYY-MM-DD)"),
    end_date: str = Query(..., description="结束日期 (YYYY-MM-DD)"),
):
    """诊断接口: 查看 daily_summary 中存储的全部设备运行时长数据 (GET - 浏览器直接调用)

    **用法示例**:
    ```
    http://localhost:8080/api/daily-summary/runtime-inspect?start_date=2026-03-01&end_date=2026-03-04
    ```

    返回 daily_summary 表中全部设备、全部指标类型的数据, 按日期分组展示,
    便于检查数据库中实际存储的运行时长、电量、投料等汇总值。
    """
    try:
        # 1. 解析日期进行基本校验
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        if start_dt > end_dt:
            return ApiResponse.fail(
                f"日期范围错误: start_date({start_date}) > end_date({end_date})"
            )

        total_days = (end_dt - start_dt).days + 1
        if total_days > 120:
            return ApiResponse.fail(
                f"日期范围过大: {total_days}天, 最大支持120天"
            )

        # 2. 调用 service 查询
        # [FIX] InfluxDB 查询在线程池中执行, 避免阻塞事件循环
        service = get_daily_summary_service()
        result = await asyncio.to_thread(
            service.get_all_runtime_inspect,
            start_date=start_date,
            end_date=end_date,
        )
        return ApiResponse.ok(result)

    except ValueError as e:
        return ApiResponse.fail(f"日期格式错误: {str(e)}, 请使用 YYYY-MM-DD 格式")
    except Exception as e:
        logger.error("[DailySummary] runtime-inspect failed: %s", e, exc_info=True)
        return ApiResponse.fail(f"查询失败: {str(e)}")
