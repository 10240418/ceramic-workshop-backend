# ============================================================
# 文件说明: daily_summary.py - 日汇总数据管理API
# ============================================================
# 接口列表:
# 1. POST /api/daily-summary/calculate        - 手动计算指定日期的汇总数据
# 2. POST /api/daily-summary/fill-missing     - 检测并补全缺失日期
# 3. GET  /api/daily-summary/available-dates  - 获取已有的日期列表
# 4. GET  /api/daily-summary/query            - 查询日汇总数据
# ============================================================

from fastapi import APIRouter, Query
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.models.response import ApiResponse
from app.services.daily_summary_service import get_daily_summary_service

router = APIRouter(prefix="/api/daily-summary", tags=["日汇总数据管理"])


# ============================================================
# 1. POST /api/daily-summary/calculate - 手动计算日汇总
# ============================================================
@router.post("/calculate")
async def calculate_daily_summary(
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
        return ApiResponse.fail(f"计算失败: {str(e)}")


# ============================================================
# 2. POST /api/daily-summary/fill-missing - 补全缺失日期
# ============================================================
@router.post("/fill-missing")
async def fill_missing_dates(
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
        return ApiResponse.fail(f"补全失败: {str(e)}")


# ============================================================
# 3. GET /api/daily-summary/available-dates - 获取已有日期
# ============================================================
@router.get("/available-dates")
async def get_available_dates():
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
        return ApiResponse.fail(f"查询失败: {str(e)}")


# ============================================================
# 4. GET /api/daily-summary/query - 查询日汇总数据
# ============================================================
@router.get("/query")
async def query_daily_summary(
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
        # 解析日期
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        
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
        return ApiResponse.fail(f"查询失败: {str(e)}")

