# 料仓设备API路由

from fastapi import APIRouter, Query, Path
from typing import Optional, List
from datetime import datetime, timedelta

from app.models.response import ApiResponse
from app.services.history_query_service import get_history_service
from app.services.polling_service import (
    get_latest_data,
    get_latest_device_data,
    get_latest_devices_by_type,
    get_latest_timestamp,
    is_polling_running
)
# 引入投料分析服务
from app.services.feeding_analysis_service import manual_analyze_feeding
# 引入 InfluxDB 写入
from app.core.influxdb import get_influx_client, write_points_batch
from influxdb_client import Point
from influxdb_client.client.write_api import SYNCHRONOUS
from config import get_settings

router = APIRouter(prefix="/api/hopper", tags=["料仓设备"])
# 🔧 删除模块级实例化，改为在函数内调用 get_history_service()


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
    - 🚀 从内存缓存读取，响应速度极快（<1ms）
    - 📊 适合大屏实时监控
    - ⚡ 无数据库压力
    
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
    interval: Optional[str] = Query("5m", description="聚合间隔", example="5m")
):
    """获取料仓设备的历史数据
    
    **可用字段**:
    - WeighSensor: `weight`, `feed_rate`
    - TemperatureSensor: `temperature`
    - ElectricityMeter: `Pt`, `ImpEp`, `Ua_0`, `Ua_1`, `Ua_2`, `I_0`, `I_1`, `I_2`
    
    **时间范围**: 默认查询最近1小时
    
    **示例**:
    ```
    GET /api/hopper/short_hopper_1/history
    GET /api/hopper/short_hopper_1/history?module_type=WeighSensor&fields=weight,feed_rate
    GET /api/hopper/short_hopper_1/history?start=2025-12-10T00:00:00&end=2025-12-10T12:00:00
    ```
    """
    try:
        # 默认时间范围：最近1小时
        if not start:
            start = datetime.now() - timedelta(hours=1)
        if not end:
            end = datetime.now()
        
        # 解析字段列表
        field_list = fields.split(",") if fields else None
        
        data = get_history_service().query_device_history(
            device_id=device_id,
            start=start,
            end=end,
            module_type=module_type,
            fields=field_list,
            interval=interval
        )
        
        return ApiResponse.ok({
            "device_id": device_id,
            "time_range": {
                "start": start.isoformat(),
                "end": end.isoformat()
            },
            "interval": interval,
            "data": data
        })
    except Exception as e:
        return ApiResponse.fail(f"查询失败: {str(e)}")


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
             from app.core.timezone_utils import BEIJING_TZ
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
        from app.core.timezone_utils import BEIJING_TZ
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
# 7. POST /api/hopper/feeding-analysis/trigger - 手动触发投料分析
# ============================================================
@router.post("/feeding-analysis/trigger")
async def trigger_feeding_analysis(
    device_ids: Optional[List[str]] = Query(
        None,
        description="指定设备ID列表，为空则分析所有料仓",
        example=["short_hopper_1", "long_hopper_1"]
    )
):
    """
    手动触发投料分析任务
    
    **用途**:
    - 前端手动刷新投料记录
    - 测试投料分析算法
    - 补充分析遗漏的数据
    
    **返回结果**:
    ```json
    {
        "success": true,
        "data": {
            "total_devices": 7,
            "devices_with_events": 3,
            "total_events": 5,
            "details": [
                {"device_id": "short_hopper_1", "events_count": 2},
                {"device_id": "long_hopper_2", "events_count": 3}
            ]
        }
    }
    ```
    """
    try:
        stats = await manual_analyze_feeding(device_ids)
        return ApiResponse.ok(stats)
    except Exception as e:
        return ApiResponse.fail(f"触发投料分析失败: {str(e)}")


# ============================================================
# 8. GET /api/hopper/feeding-analysis/status - 获取投料分析服务状态
# ============================================================
@router.get("/feeding-analysis/status")
async def get_feeding_analysis_status():
    """
    获取投料分析服务的运行状态
    
    **返回信息**:
    - 服务是否运行
    - 检测频率
    - 查询窗口
    - 算法参数
    """
    try:
        from app.services.feeding_analysis_service import feeding_service
        
        return ApiResponse.ok({
            "is_running": feeding_service._is_running,
            "run_interval_minutes": feeding_service.run_interval_minutes,
            "query_window_minutes": feeding_service.query_window_minutes,
            "use_raw_data": feeding_service.use_raw_data,
            "algorithm_params": {
                "min_feeding_threshold": feeding_service.min_feeding_threshold,
                "rising_step_threshold": feeding_service.rising_step_threshold,
                "drop_threshold": feeding_service.drop_threshold,
                "lookahead_steps": feeding_service.lookahead_steps
            }
        })
    except Exception as e:
        return ApiResponse.fail(f"获取状态失败: {str(e)}")

