# 料仓设备API路由

from fastapi import APIRouter, Query, Path
from typing import Optional, List
from datetime import datetime, timedelta

from app.models.response import ApiResponse
from app.core.unified_naming import parse_history_fields
from app.services.history_query_service import get_history_service
from app.services.polling_service import (
    get_latest_data,
    get_latest_device_data,
    get_latest_devices_by_type,
    get_latest_timestamp,
    is_polling_running
)
# 引入投料分析服务
from app.services.feeding_analysis_service import feeding_analysis_service
# 引入 InfluxDB 写入
from app.core.influxdb import get_influx_client, write_points_batch
from influxdb_client import Point
from influxdb_client.client.write_api import SYNCHRONOUS
from config import get_settings

router = APIRouter(prefix="/api/hopper", tags=["料仓设备"])
# [FIX] 删除模块级实例化，改为在函数内调用 get_history_service()


HOPPER_TYPES = ["short_hopper", "no_hopper", "long_hopper"]


# 静态设备列表（避免查询 InfluxDB）
HOPPER_DEVICES = {
    "short_hopper": [
        {"device_id": "short_hopper_1", "device_type": "short_hopper", "db_number": "8"},
        {"device_id": "short_hopper_2", "device_type": "short_hopper", "db_number": "8"},
        {"device_id": "short_hopper_3", "device_type": "short_hopper", "db_number": "8"},
        {"device_id": "short_hopper_4", "device_type": "short_hopper", "db_number": "8"},
    ],
    "no_hopper": [
        {"device_id": "no_hopper_1", "device_type": "no_hopper", "db_number": "8"},
        {"device_id": "no_hopper_2", "device_type": "no_hopper", "db_number": "8"},
    ],
    "long_hopper": [
        {"device_id": "long_hopper_1", "device_type": "long_hopper", "db_number": "8"},
        {"device_id": "long_hopper_2", "device_type": "long_hopper", "db_number": "8"},
        {"device_id": "long_hopper_3", "device_type": "long_hopper", "db_number": "8"},
    ],
}


# ============================================================
# 1. GET /api/hopper/realtime/batch - 批量获取所有料仓实时数据（内存缓存）
# ============================================================
@router.get("/realtime/batch")
async def get_all_hoppers_realtime(
    hopper_type: Optional[str] = Query(
        None,
        description="料仓类型筛选",
        enum=["short_hopper", "no_hopper", "long_hopper"],
        example="short_hopper"
    )
):
    """批量获取所有料仓的实时数据（从内存缓存读取，无需查询数据库）
    
    **优势**:
    - [START] 从内存缓存读取，响应速度极快（<1ms）
    - [DATA] 适合大屏实时监控
    - [重要] 无数据库压力
    
    **数据来源**: 内存缓存（由轮询服务实时更新）
    
    **返回结构**:
    ```json
    {
        "success": true,
        "data": {
            "total": 9,
            "source": "cache",
            "timestamp": "2025-12-25T10:00:00Z",
            "polling_running": true,
            "devices": [
                {
                    "device_id": "short_hopper_1",
                    "device_type": "short_hopper",
                    "timestamp": "2025-12-11T10:00:00Z",
                    "modules": {
                        "weight": {"module_type": "WeighSensor", "fields": {"weight": 1234.5, "feed_rate": 12.3}},
                        "temp": {"module_type": "TemperatureSensor", "fields": {"temperature": 85.5}},
                        "elec": {"module_type": "ElectricityMeter", "fields": {"Pt": 120.5, "Ua_0": 230.2}}
                    }
                },
                ...
            ]
        }
    }
    ```
    """
    try:
        # 从内存缓存获取数据
        if hopper_type:
            devices_data = get_latest_devices_by_type(hopper_type)
        else:
            all_data = get_latest_data()
            devices_data = [
                data for data in all_data.values()
                if data.get('device_type') in HOPPER_TYPES
            ]
        
        # 数据有效性检查
        if not devices_data:
            return ApiResponse.ok({
                "total": 0,
                "source": "cache",
                "timestamp": get_latest_timestamp(),
                "polling_running": is_polling_running(),
                "warning": "缓存为空，轮询服务可能未启动或首次轮询未完成",
                "devices": []
            })
        
        return ApiResponse.ok({
            "total": len(devices_data),
            "source": "cache",
            "timestamp": get_latest_timestamp(),
            "polling_running": is_polling_running(),
            "devices": devices_data
        })
    except Exception as e:
        return ApiResponse.fail(f"批量查询失败: {str(e)}")


# ============================================================
# 2. GET /api/hopper/{device_id} - 获取料仓实时数据（内存缓存）
# ============================================================
@router.get("/{device_id}")
async def get_hopper_realtime(
    device_id: str = Path(
        ..., 
        description="料仓设备ID",
        example="short_hopper_1"
    )
):
    """获取指定料仓的实时数据（从内存缓存读取）
    
    **数据来源**: 内存缓存（由轮询服务实时更新）
    
    **返回字段**:
    - `weight`: 实时重量 (kg)
    - `feed_rate`: 下料速度 (kg/h)
    - `temperature`: 温度 (°C)
    - `Pt`: 功率 (kW)
    - `ImpEp`: 电能 (kWh)
    - `Ua_0~2`: 三相电压 (V)
    - `I_0~2`: 三相电流 (A)
    """
    try:
        # 优先从内存缓存读取
        cached_data = get_latest_device_data(device_id)
        
        if cached_data:
            return ApiResponse.ok({
                "source": "cache",
                **cached_data
            })
        
        # 缓存无数据，查询 InfluxDB
        data = get_history_service().query_device_realtime(device_id)
        if not data:
            return ApiResponse.fail(f"设备 {device_id} 不存在或无数据")
        return ApiResponse.ok({
            "source": "influxdb",
            **data
        })
    except Exception as e:
        return ApiResponse.fail(f"查询失败: {str(e)}")

# ============================================================
# 3. GET /api/hopper/{device_id}/history - 获取料仓历史数据（InfluxDB）
# ============================================================
@router.get("/{device_id}/history")
async def get_hopper_history(
    device_id: str = Path(..., description="料仓设备ID", example="short_hopper_1"),
    start: Optional[datetime] = Query(None, description="开始时间", example="2025-12-10T00:00:00"),
    end: Optional[datetime] = Query(None, description="结束时间", example="2025-12-10T23:59:59"),
    module_type: Optional[str] = Query(
        None, 
        description="模块类型筛选",
        enum=["WeighSensor", "TemperatureSensor", "ElectricityMeter"],
        example="WeighSensor"
    ),
    fields: Optional[str] = Query(None, description="字段筛选 (逗号分隔)", example="weight,feed_rate"),
    interval: Optional[str] = Query(None, description="聚合间隔（为空则自动计算）", example="5m"),
    auto_interval: bool = Query(True, description="是否自动计算最佳聚合间隔")
):
    """获取料仓设备的历史数据（支持动态聚合间隔）
    
    **可用字段**:
    - WeighSensor: `weight`, `feed_rate`
    - TemperatureSensor: `temperature`
    - ElectricityMeter: `Pt`, `ImpEp`, `Ua_0`, `Ua_1`, `Ua_2`, `I_0`, `I_1`, `I_2`
    
    **时间范围**: 默认查询最近1小时
    
    **动态聚合**:
    - `auto_interval=true` (默认): 根据时间范围自动计算最佳聚合间隔
    - `interval` 参数: 手动指定聚合间隔（如 "5s", "1m", "5m", "1h"）
    - 目标数据点数: 40-150 点，理想值 80 点
    
    **示例**:
    ```
    GET /api/hopper/short_hopper_1/history  # 自动聚合
    GET /api/hopper/short_hopper_1/history?interval=5m  # 手动指定5分钟聚合
    GET /api/hopper/short_hopper_1/history?auto_interval=false&interval=1m  # 强制1分钟聚合
    GET /api/hopper/short_hopper_1/history?start=2025-12-10T00:00:00&end=2025-12-10T12:00:00
    ```
    """
    try:
        # 默认时间范围：最近1小时
        if not start:
            start = datetime.now() - timedelta(hours=1)
        if not end:
            end = datetime.now()
        
        # 解析并校验字段列表（仅保留统一数据库字段）
        field_list = parse_history_fields(fields, module_type)
        
        data = get_history_service().query_device_history(
            device_id=device_id,
            start=start,
            end=end,
            module_type=module_type,
            fields=field_list,
            interval=interval,
            auto_interval=auto_interval
        )
        
        # 计算实际使用的聚合间隔（用于返回给前端）
        if auto_interval and interval is None:
            # 重新计算以返回给前端
            from app.tools.timezone_tools import BEIJING_TZ
            import datetime as dt_module
            
            def to_utc(dt: datetime) -> datetime:
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=BEIJING_TZ)
                return dt.astimezone(dt_module.timezone.utc).replace(tzinfo=None)
            
            start_utc = to_utc(start)
            end_utc = to_utc(end)
            actual_interval = get_history_service()._calculate_optimal_interval(start_utc, end_utc)
        else:
            actual_interval = interval or "1m"
        
        return ApiResponse.ok({
            "device_id": device_id,
            "time_range": {
                "start": start.isoformat(),
                "end": end.isoformat()
            },
            "interval": actual_interval,
            "auto_interval": auto_interval,
            "data_points": len(data),
            "data": data
        })
    except Exception as e:
        return ApiResponse.fail(f"查询失败: {str(e)}")


# ============================================================
# 2.5 GET /api/hopper/{device_id}/feeding-cumulative - 查询下料速度和投料总量历史
# ============================================================
@router.get("/{device_id}/feeding-cumulative")
async def get_hopper_feeding_cumulative(
    device_id: str = Path(..., description="设备ID (如 short_hopper_1)"),
    start: Optional[datetime] = Query(None, description="开始时间"),
    end: Optional[datetime] = Query(None, description="结束时间"),
    fields: Optional[str] = Query(None, description="字段 (逗号分隔)", example="display_feed_rate,feeding_total"),
    auto_interval: bool = Query(True, description="是否自动计算聚合间隔"),
):
    """
    查询料仓的下料速度 (display_feed_rate) 和投料总量 (feeding_total) 历史

    数据来源: feeding_cumulative measurement (由 feeding_analysis_service v5.0 写入)
    
    **可查询字段**:
    - `display_feed_rate`: 显示下料速度 (kg/h, 可正可负)
    - `feeding_total`: 投料总量 (kg, 只增不减)
    """
    try:
        svc = get_history_service()
        
        if not start:
            start = datetime.now() - timedelta(hours=24)
        if not end:
            end = datetime.now()
        
        field_list = fields.split(",") if fields else None
        
        data, actual_interval = svc.query_feeding_cumulative_history(
            device_id=device_id,
            start=start,
            end=end,
            fields=field_list,
            auto_interval=auto_interval,
        )
        
        return ApiResponse.ok({
            "time_range": {
                "start": start.isoformat(),
                "end": end.isoformat(),
            },
            "interval": actual_interval,
            "data_points": len(data),
            "data": data,
        })
    except Exception as e:
        return ApiResponse.fail(f"查询下料速度/投料总量失败: {str(e)}")


# ============================================================
# 3. GET /api/hopper/{device_id}/feeding-history
# ============================================================
@router.get("/{device_id}/feeding-history")
async def get_hopper_feeding_history(
    device_id: str = Path(..., description="设备ID (如 short_hopper_1)"),
    start: Optional[datetime] = Query(None, description="开始时间"),
    end: Optional[datetime] = Query(None, description="结束时间"),
    limit: int = 5000  # 增加默认上限
):
    """
    查询料仓的自动投料分析记录 (Feeding Analysis)
    """
    try:
        svc = get_history_service()
        
        # 默认最近7天
        if not start:
            start = datetime.now() - timedelta(days=7)
        if not end:
            end = datetime.now()
            
        # 使用 Service 统一封装的方法，自动处理时区
        records = svc.query_feeding_history(
            device_id=device_id,
            start=start,
            end=end,
            limit=limit
        )
        
        return ApiResponse.ok(data=records)
    except Exception as e:
        return ApiResponse.fail(f"查询投料记录失败: {e}")


# ============================================================
# 4. POST /api/hopper/{device_id}/feeding-history/backfill - 客户端回填/校正投料记录
# ============================================================
@router.post("/{device_id}/feeding-history/backfill")
async def backfill_hopper_feeding_record(
    device_id: str,
    record: dict
):
    """
    客户端计算后回填漏掉的投料记录
    
    Payload Example:
    {
        "time": "2025-01-18T12:00:00Z",
        "added_weight": 505.5,
        "raw_increase": 480.0,
        "compensation": 25.5,
        "duration_intervals": 3
    }
    """
    try:
        # 解析时间
        time_val = record.get("time")
        if not time_val:
            return ApiResponse.fail("Missing time field")
            
        dt = datetime.fromisoformat(str(time_val).replace("Z", "+00:00"))
        
        # 构造 Point
        p = Point("feeding_records") \
            .tag("device_id", device_id) \
            .field("added_weight", float(record.get("added_weight", 0))) \
            .field("raw_increase", float(record.get("raw_increase", 0))) \
            .field("duration_intervals", int(record.get("duration_intervals", 0))) \
            .field("compensation", float(record.get("compensation", 0))) \
            .field("source", "client_backfill") \
            .time(dt)

        # 写入 InfluxDB
        client = get_influx_client()
        write_api = client.write_api(write_options=SYNCHRONOUS)
        write_api.write(bucket=get_settings().influx_bucket, record=p)
        
        return ApiResponse.ok({"message": "Record backfilled successfully"})
    except Exception as e:
        return ApiResponse.fail(f"Backfill fail: {str(e)}")


# ============================================================
# 5. DELETE /api/hopper/{device_id}/feeding-history - 删除错误的投料记录
# ============================================================
@router.delete("/{device_id}/feeding-history")
async def delete_hopper_feeding_record(
    device_id: str = Path(..., description="设备ID"),
    time: datetime = Query(..., description="记录时间 (ISO format)"),
):
    """
    删除指定的投料记录 (例如: 前端检测为误判)
    注意: time 必须严格匹配记录的时间戳
    """
    try:
        # 确保时间为 UTC
        if time.tzinfo is None:
             # 如果传来的是 naive time (通常认为是北京时间)，转 UTC
             from app.tools.timezone_tools import BEIJING_TZ
             time = time.replace(tzinfo=BEIJING_TZ).astimezone(datetime.timezone.utc)
        
        # 调用 InfluxDB 删除
        # delete_predicate 是根据时间范围和 tag 来删的
        # 为了精确删除一个点，我们将 start 和 stop 设为 time-1s 和 time+1s
        start = time - timedelta(seconds=1)
        stop = time + timedelta(seconds=1)
        
        predicate = f'_measurement="feeding_records" AND device_id="{device_id}"'
        
        client = get_influx_client()
        delete_api = client.delete_api()
        
        # InfluxDB delete API 需要 start/stop 作为字符串或 datetime
        delete_api.delete(
            start=start,
            stop=stop,
            predicate=predicate,
            bucket=get_settings().influx_bucket,
            org=get_settings().influx_org
        )
        
        return ApiResponse.ok({"message": f"Deleted record at {time}"})
    except Exception as e:
        return ApiResponse.fail(f"Delete fail: {str(e)}")


# ============================================================
# 6. DELETE /api/hopper/{device_id}/feeding-history/purge - 批量清理投料记录
# ============================================================
@router.delete("/{device_id}/feeding-history/purge")
async def purge_hopper_feeding_records(
    device_id: str = Path(..., description="设备ID"),
    start: datetime = Query(..., description="开始时间 (ISO format)"),
    end: datetime = Query(..., description="结束时间 (ISO format)"),
):
    """
    批量删除指定时间范围内的所有投料记录 (用于清理脏数据)
    
    示例: DELETE /api/hopper/long_hopper_1/feeding-history/purge?start=2026-01-17T00:00:00&end=2026-01-19T00:00:00
    """
    try:
        from app.tools.timezone_tools import BEIJING_TZ
        import datetime as dt_module
        
        # 确保时间为 UTC
        def to_utc(t: datetime) -> datetime:
            if t.tzinfo is None:
                t = t.replace(tzinfo=BEIJING_TZ)
            return t.astimezone(dt_module.timezone.utc)
        
        start_utc = to_utc(start)
        end_utc = to_utc(end)
        
        predicate = f'_measurement="feeding_records" AND device_id="{device_id}"'
        
        client = get_influx_client()
        delete_api = client.delete_api()
        
        delete_api.delete(
            start=start_utc,
            stop=end_utc,
            predicate=predicate,
            bucket=get_settings().influx_bucket,
            org=get_settings().influx_org
        )
        
        return ApiResponse.ok({
            "message": f"Purged all feeding_records for {device_id} between {start} and {end}"
        })
    except Exception as e:
        return ApiResponse.fail(f"Purge fail: {str(e)}")


# ============================================================



# ============================================================
# 8. GET /api/hopper/feeding-analysis/status - 获取投料分析服务状态
# ============================================================
@router.get("/feeding-analysis/status")
async def get_feeding_analysis_status():
    """
    获取投料分析服务 v6.0 的运行状态

    返回: 7个料仓的 显示下料速度 / 投料总量 / 上料状态 / 缓存补偿量
    """
    try:
        from app.services.feeding_analysis_service import (
            feeding_analysis_service,
            WINDOW_MAX_LEN,
            CALC_INTERVAL,
            DEAD_ZONE_KG,
        )

        return ApiResponse.ok({
            "version": "v6.0",
            "algorithm": "sliding_window",
            "window_size": WINDOW_MAX_LEN,
            "calc_interval": CALC_INTERVAL,
            "dead_zone_kg": DEAD_ZONE_KG,
            "devices": feeding_analysis_service.get_all_feeding_data(),
        })
    except Exception as e:
        return ApiResponse.fail(f"获取状态失败: {str(e)}")


