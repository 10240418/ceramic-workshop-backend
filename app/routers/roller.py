# ============================================================
# 文件说明: roller.py - 辊道窑设备API路由
# ============================================================
# 接口列表:
# 1. GET /api/roller/info              - 获取辊道窑信息
# 2. GET /api/roller/realtime          - 获取辊道窑实时数据（内存缓存）
# 3. GET /api/roller/history           - 获取辊道窑历史数据
# 4. GET /api/roller/zone/{zone_id}    - 获取指定温区数据
# ============================================================

from fastapi import APIRouter, Query, Path
from typing import Optional
from datetime import datetime, timedelta
import logging

from app.models.response import ApiResponse

logger = logging.getLogger(__name__)
from app.core.unified_naming import parse_history_fields
from app.services.history_query_service import get_history_service
from app.services.polling_service import (
    get_latest_device_data,
    get_latest_timestamp,
    is_polling_running
)

router = APIRouter(prefix="/api/roller", tags=["辊道窑设备"])

# [FIX] 删除模块级实例化，改为在函数内调用 get_history_service()

# 辊道窑设备ID
ROLLER_KILN_ID = "roller_kiln_1"

# 温区标签
ZONE_TAGS = ["zone1", "zone2", "zone3", "zone4", "zone5", "zone6"]


# ============================================================
# 1. GET /api/roller/info - 获取辊道窑信息
# ============================================================
@router.get("/info")
async def get_roller_info():
    """获取辊道窑设备信息
    
    **返回**:
    - 设备基本信息
    - 温区配置
    - 电表配置
    """
    return ApiResponse.ok({
        "device_id": ROLLER_KILN_ID,
        "device_name": "辊道窑1号",
        "device_type": "roller_kiln",
        "zones": [
            {"zone_id": "zone1", "name": "1号温区"},
            {"zone_id": "zone2", "name": "2号温区"},
            {"zone_id": "zone3", "name": "3号温区"},
            {"zone_id": "zone4", "name": "4号温区"},
            {"zone_id": "zone5", "name": "5号温区"},
            {"zone_id": "zone6", "name": "6号温区"},
        ],
        "meters": [
            {"meter_id": "main_meter", "name": "主电表"},
            {"meter_id": "zone1_meter", "name": "1号区电表"},
            {"meter_id": "zone2_meter", "name": "2号区电表"},
            {"meter_id": "zone3_meter", "name": "3号区电表"},
            {"meter_id": "zone4_meter", "name": "4号区电表"},
            {"meter_id": "zone5_meter", "name": "5号区电表"},
        ]
    })


# ============================================================
# 2. GET /api/roller/realtime - 获取辊道窑实时数据（内存缓存）
# ============================================================
@router.get("/realtime")
async def get_roller_realtime():
    """获取辊道窑所有温区和电表的实时数据（从内存缓存读取）
    
    **数据来源**: 内存缓存（由轮询服务实时更新）
    
    **返回字段**:
    - 6个温区的 `temperature`
    - 6个电表的 `Pt`, `ImpEp`, `Ua_0~2`, `I_0~2`
    """
    try:
        # 优先从内存缓存读取
        cached_data = get_latest_device_data(ROLLER_KILN_ID)
        
        if cached_data:
            return ApiResponse.ok({
                "source": "cache",
                "polling_running": is_polling_running(),
                **cached_data
            })
        
        # 缓存无数据，查询 InfluxDB
        data = get_history_service().query_device_realtime(ROLLER_KILN_ID)
        if not data:
            return ApiResponse.fail("辊道窑设备无数据")
        return ApiResponse.ok({
            "source": "influxdb",
            **data
        })
    except Exception as e:
        logger.error("[Roller] query realtime failed: %s", e, exc_info=True)
        return ApiResponse.fail(f"查询失败: {str(e)}")


# ============================================================
# 2.1 GET /api/roller/realtime/formatted - 格式化实时数据
# ============================================================
@router.get("/realtime/formatted")
async def get_roller_realtime_formatted():
    """获取辊道窑格式化后的实时数据（前端友好格式）
    
    **返回结构**:
    ```json
    {
      "device_id": "roller_kiln_1",
      "timestamp": "2025-12-11T10:00:00Z",
      "zones": [
        {
          "zone_id": "zone1",
          "temperature": 820.0,
                    "Pt": 38.0,
                    "ImpEp": 1250.0,
                    "Ua_0": 220.0,
                    "I_0": 100.0,
                    "I_1": 100.0,
                    "I_2": 100.0
        },
        ...  // zone2-zone6
      ],
      "total": {
                "Pt": 240.0,
                "ImpEp": 8500.0,
                "Ua_0": 220.0,
                "I_0": 600.0,
                "I_1": 600.0,
                "I_2": 600.0
      }
    }
    ```
    
    **说明**:
    - zones: 6个分区电表数据（zone1-zone6）
    - total: 总表数据（6个分区之和，由后端计算）
    - 电流变比为60，返回的电流数据已经乘以变比后的一次侧实际电流
    """
    try:
        # 优先从内存缓存读取（与其他API保持一致）
        cached_data = get_latest_device_data(ROLLER_KILN_ID)
        
        if cached_data:
            raw_data = cached_data
        else:
            # 缓存无数据，回退到 InfluxDB 查询
            raw_data = get_history_service().query_device_realtime(ROLLER_KILN_ID)
        
        if not raw_data:
            return ApiResponse.fail("辊道窑设备无数据")
        
        modules = raw_data.get("modules", {})
        
        # 格式化温区数据 (6个分区)
        zones = []
        for i in range(1, 7):
            zone_id = f"zone{i}"
            temp_tag = f"zone{i}_temp"
            meter_tag = f"zone{i}_meter"
            
            meter_fields = modules.get(meter_tag, {}).get("fields", {})
            
            zone_data = {
                "zone_id": zone_id,
                "zone_name": f"{i}号温区",
                "temperature": modules.get(temp_tag, {}).get("fields", {}).get("temperature", 0.0),
                "Pt": meter_fields.get("Pt", 0.0),
                "ImpEp": meter_fields.get("ImpEp", 0.0),
                "Ua_0": meter_fields.get("Ua_0", 0.0),
                "I_0": meter_fields.get("I_0", 0.0),
                "I_1": meter_fields.get("I_1", 0.0),
                "I_2": meter_fields.get("I_2", 0.0),
            }
            zones.append(zone_data)
        
        # 获取总表数据（从缓存中读取后端计算的总值）
        total_cached = get_latest_device_data("roller_kiln_total")
        
        if total_cached:
            total_fields = total_cached.get("modules", {}).get("total_meter", {}).get("fields", {})
            total_data = {
                "Pt": total_fields.get("Pt", 0.0),
                "ImpEp": total_fields.get("ImpEp", 0.0),
                "Ua_0": total_fields.get("Ua_0", 0.0),
                "I_0": total_fields.get("I_0", 0.0),
                "I_1": total_fields.get("I_1", 0.0),
                "I_2": total_fields.get("I_2", 0.0),
            }
        else:
            # 如果总表缓存不存在，前端可以自行累加
            total_data = {
                "Pt": sum(z["Pt"] for z in zones),
                "ImpEp": sum(z["ImpEp"] for z in zones),
                "Ua_0": sum(z["Ua_0"] for z in zones) / 6 if zones else 0.0,
                "I_0": sum(z["I_0"] for z in zones),
                "I_1": sum(z["I_1"] for z in zones),
                "I_2": sum(z["I_2"] for z in zones),
            }
        
        formatted_data = {
            "device_id": raw_data.get("device_id"),
            "timestamp": raw_data.get("timestamp"),
            "zones": zones,
            "total": total_data
        }
        
        return ApiResponse.ok(formatted_data)
    except Exception as e:
        logger.error("[Roller] query formatted realtime failed: %s", e, exc_info=True)
        return ApiResponse.fail(f"查询失败: {str(e)}")


# ============================================================
# 3. GET /api/roller/history - 获取辊道窑历史数据
# ============================================================
@router.get("/history")
async def get_roller_history(
    start: Optional[datetime] = Query(None, description="开始时间", example="2025-12-10T00:00:00"),
    end: Optional[datetime] = Query(None, description="结束时间", example="2025-12-10T23:59:59"),
    module_type: Optional[str] = Query(
        None, 
        description="模块类型筛选",
        enum=["TemperatureSensor", "ElectricityMeter"],
        example="TemperatureSensor"
    ),
    zone: Optional[str] = Query(
        None, 
        description="温区筛选",
        enum=["zone1", "zone2", "zone3", "zone4", "zone5", "zone6"],
        example="zone1"
    ),
    fields: Optional[str] = Query(None, description="字段筛选 (逗号分隔)", example="temperature"),
    interval: Optional[str] = Query("5m", description="聚合间隔", example="5m")
):
    """获取辊道窑历史数据
    
    **可用字段**:
    - TemperatureSensor: `temperature`
    - ElectricityMeter: `Pt`, `ImpEp`, `Ua_0`, `Ua_1`, `Ua_2`, `I_0`, `I_1`, `I_2`
    
    **示例**:
    ```
    GET /api/roller/history
    GET /api/roller/history?module_type=TemperatureSensor
    GET /api/roller/history?zone=zone1&fields=temperature
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
        
        # 构建 module_tag 筛选
        module_tag = f"{zone}_temp" if zone and module_type == "TemperatureSensor" else None
        if zone and module_type == "ElectricityMeter":
            module_tag = f"{zone}_meter"
        
        data = get_history_service().query_device_history(
            device_id=ROLLER_KILN_ID,
            start=start,
            end=end,
            module_type=module_type,
            module_tag=module_tag,
            fields=field_list,
            interval=interval
        )
        
        return ApiResponse.ok({
            "device_id": ROLLER_KILN_ID,
            "time_range": {
                "start": start.isoformat(),
                "end": end.isoformat()
            },
            "interval": interval,
            "zone": zone,
            "data": data
        })
    except Exception as e:
        logger.error("[Roller] query history failed: %s", e, exc_info=True)
        return ApiResponse.fail(f"查询失败: {str(e)}")


# ============================================================
# 4. GET /api/roller/zone/{zone_id} - 获取指定温区实时数据
# ============================================================
@router.get("/zone/{zone_id}")
async def get_zone_realtime(
    zone_id: str = Path(
        ..., 
        description="温区ID",
        example="zone1"
    )
):
    """获取指定温区的实时温度和功率数据
    
    **可用温区**: zone1, zone2, zone3, zone4, zone5, zone6
    
    **返回**:
    - `temperature`: 当前温度
    - `Pt`: 当前功率
    - `ImpEp`: 累计电能
    
    **示例**:
    ```
    GET /api/roller/zone/zone1
    GET /api/roller/zone/zone3
    ```
    """
    if zone_id not in ZONE_TAGS:
        return ApiResponse.fail(f"无效的温区ID: {zone_id}，可用: {ZONE_TAGS}")
    
    try:
        # 查询设备实时数据
        data = get_history_service().query_device_realtime(ROLLER_KILN_ID)
        if not data:
            return ApiResponse.fail("辊道窑设备无数据")
        
        # 提取指定温区的数据
        modules = data.get("modules", {})
        zone_temp = modules.get(f"{zone_id}_temp", {})
        zone_meter = modules.get(f"{zone_id}_meter", {})
        
        return ApiResponse.ok({
            "zone_id": zone_id,
            "temperature": zone_temp.get("fields", {}),
            "electricity": zone_meter.get("fields", {})
        })
    except Exception as e:
        logger.error("[Roller] query zone realtime failed: %s", e, exc_info=True)
        return ApiResponse.fail(f"查询失败: {str(e)}")
