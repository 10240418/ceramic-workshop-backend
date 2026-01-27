# ============================================================
# 文件说明: export.py - 数据导出API路由
# ============================================================
# 接口列表:
# 1. GET /api/export/runtime/all          - 所有设备设备运行时长（按天）
# 2. GET /api/export/gas-consumption      - 燃气消耗统计（按天，仅SCR燃气表）
# 3. GET /api/export/feeding-amount       - 累计投料量（按天，仅带料仓的回转窑）
# 4. GET /api/export/electricity/all      - 所有设备电量统计（按天，除燃气表外全部设备）
# 5. GET /api/export/comprehensive        - 综合导出所有数据（按天）
# ============================================================
# 设备清单:
# - 回转窑（9个）: short_hopper_1~4, no_hopper_1~2, long_hopper_1~3
#   对应前端: 窑7,6,5,4,2,1,8,3,9
# - 辊道窑（7个）: zone1~6（6个分区）+ roller_kiln_total（合计）
#   对应前端: 辊道窑分区1-6 + 辊道窑合计
# - SCR燃气表（2个）: scr_1, scr_2
#   对应前端: SCR北_燃气表, SCR南_燃气表
# - SCR氨水泵（2个）: scr_1_pump, scr_2_pump
#   对应前端: SCR北_氨水泵, SCR南_氨水泵
# - 风机（2个）: fan_1, fan_2
#   对应前端: SCR北_风机, SCR南_风机
# ============================================================

from fastapi import APIRouter, Query
from datetime import datetime, timedelta, timezone
from typing import Optional, List

from app.models.response import ApiResponse
from app.services.data_export_service import get_export_service
from app.services.data_export_service_v2 import get_export_service_v2
from app.services.data_export_service_v3 import get_export_service_v3
from app.utils.time_slice_utils import parse_days_parameter

router = APIRouter(prefix="/api/export", tags=["数据导出统计"])


# ============================================================
# 1. GET /api/export/runtime/all - 所有设备设备运行时长（按天）
# ============================================================
@router.get("/runtime/all")
async def export_all_runtime(
    start_time: Optional[str] = Query(None, description="开始时间 (ISO 8601格式)"),
    end_time: Optional[str] = Query(None, description="结束时间 (ISO 8601格式)"),
    days: Optional[int] = Query(7, description="查询最近N天（如果未指定start_time和end_time）"),
    version: Optional[str] = Query("v3", description="版本选择: v1(实时计算), v3(优化版，推荐)")
):
    """导出所有设备设备运行时长（按天）
    
    **功能说明**:
    - 统计所有设备的运行时长（基于功率 > 0.01kW 判断）
    - 按天返回：起始时间、终止时间、当日运行时长
    - 一次性获取所有设备运行时长数据
    
    **设备列表**:
    - 9个回转窑（料仓）
    - 6个辊道窑分区 + 1个辊道窑合计
    - 2个SCR氨水泵
    - 2个风机
    - **总计**: 20个设备
    
    **时间参数**:
    - 方式1: 指定 start_time 和 end_time（ISO 8601格式）
    - 方式2: 使用 days 参数查询最近N天（默认7天）
    
    **返回结构**:
    ```json
    {
        "success": true,
        "data": {
            "start_time": "2026-01-26T00:00:00Z",
            "end_time": "2026-01-28T23:59:59Z",
            "hoppers": [
                {
                    "device_id": "short_hopper_1",
                    "device_type": "hopper",
                    "total_days": 3,
                    "daily_records": [
                        {
                            "day": 1,
                            "date": "2026-01-26",
                            "start_time": "2026-01-26T00:00:00Z",
                            "end_time": "2026-01-26T23:59:59Z",
                            "runtime_hours": 18.50
                        },
                        ...
                    ]
                },
                ...
            ],
            "roller_kiln_zones": [...],  # 6个分区
            "roller_kiln_total": {...},  # 合计（平均值）
            "scr_devices": [...],        # 2个氨水泵
            "fan_devices": [...]         # 2个风机
        }
    }
    ```
    
    **示例**:
    ```
    # 查询最近7天所有设备运行时长
    GET /api/export/runtime/all
    
    # 查询最近30天所有设备运行时长
    GET /api/export/runtime/all?days=30
    
    # 查询指定时间段所有设备运行时长
    GET /api/export/runtime/all?start_time=2026-01-01T00:00:00Z&end_time=2026-01-31T23:59:59Z
    ```
    """
    try:
        # 解析时间参数
        if start_time and end_time:
            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        else:
            end_dt = datetime.now(timezone.utc)
            start_dt = end_dt - timedelta(days=days)
        
        # 选择服务版本
        if version == "v3":
            # V3: 优化版（使用预计算数据）
            service = get_export_service_v3()
            result = service.export_runtime_v3(
                start_time=start_dt,
                end_time=end_dt
            )
        else:
            # V1: 实时计算
            service = get_export_service()
            result = service.calculate_all_devices_runtime_by_day(
                start_time=start_dt,
                end_time=end_dt
            )
        
        return ApiResponse.ok(result)
    
    except ValueError as e:
        return ApiResponse.fail(f"参数错误: {str(e)}")
    except Exception as e:
        return ApiResponse.fail(f"查询失败: {str(e)}")


# ============================================================
# 2. GET /api/export/gas-consumption - 燃气消耗统计（按天）
# ============================================================
@router.get("/gas-consumption")
async def export_gas_consumption(
    device_ids: Optional[str] = Query("scr_1,scr_2", description="设备ID列表（逗号分隔），如: scr_1,scr_2"),
    start_time: Optional[str] = Query(None, description="开始时间 (ISO 8601格式)"),
    end_time: Optional[str] = Query(None, description="结束时间 (ISO 8601格式)"),
    days: Optional[int] = Query(7, description="查询最近N天（如果未指定start_time和end_time）"),
    version: Optional[str] = Query("v3", description="版本选择: v1(实时计算), v3(优化版，推荐)")
):
    """导出燃气消耗统计（按天，仅SCR燃气表）
    
    **功能说明**:
    - 统计SCR设备的燃气表读数（total_flow字段）
    - 按天返回：起始读数、截止读数、当日消耗
    - **仅包含**: scr_1, scr_2（燃气表）
    
    **设备列表**:
    - scr_1: SCR北_燃气表
    - scr_2: SCR南_燃气表
    
    **时间参数**:
    - 方式1: 指定 start_time 和 end_time（ISO 8601格式）
    - 方式2: 使用 days 参数查询最近N天（默认7天）
    
    **返回结构**:
    ```json
    {
        "success": true,
        "data": {
            "scr_1": {
                "device_id": "scr_1",
                "total_days": 3,
                "daily_records": [
                    {
                        "day": 1,
                        "date": "2026-01-26",
                        "start_time": "2026-01-26T00:00:00Z",
                        "end_time": "2026-01-26T23:59:59Z",
                        "start_reading": 1234.56,
                        "end_reading": 1456.78,
                        "consumption": 222.22
                    },
                    ...
                ]
            },
            "scr_2": {...}
        }
    }
    ```
    
    **示例**:
    ```
    # 查询最近7天
    GET /api/export/gas-consumption
    
    # 查询最近30天
    GET /api/export/gas-consumption?days=30
    
    # 查询指定时间段
    GET /api/export/gas-consumption?start_time=2026-01-01T00:00:00Z&end_time=2026-01-31T23:59:59Z
    
    # 查询单个设备
    GET /api/export/gas-consumption?device_ids=scr_1
    ```
    """
    try:
        # 解析设备ID列表
        device_id_list = [d.strip() for d in device_ids.split(",")]
        
        # 解析时间参数
        if start_time and end_time:
            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        else:
            end_dt = datetime.now(timezone.utc)
            start_dt = end_dt - timedelta(days=days)
        
        # 选择服务版本
        if version == "v3":
            # V3: 优化版（使用预计算数据）
            service = get_export_service_v3()
            result = service.export_gas_v3(
                device_ids=device_id_list,
                start_time=start_dt,
                end_time=end_dt
            )
        else:
            # V1: 实时计算
            service = get_export_service()
            result = service.calculate_gas_consumption_by_day(
                device_ids=device_id_list,
                start_time=start_dt,
                end_time=end_dt
            )
        
        return ApiResponse.ok(result)
    
    except ValueError as e:
        return ApiResponse.fail(f"参数错误: {str(e)}")
    except Exception as e:
        return ApiResponse.fail(f"查询失败: {str(e)}")


# ============================================================
# 3. GET /api/export/feeding-amount - 累计投料量（按天）
# ============================================================
@router.get("/feeding-amount")
async def export_feeding_amount(
    start_time: Optional[str] = Query(None, description="开始时间 (ISO 8601格式)"),
    end_time: Optional[str] = Query(None, description="结束时间 (ISO 8601格式)"),
    days: Optional[int] = Query(7, description="查询最近N天（如果未指定start_time和end_time）"),
    version: Optional[str] = Query("v3", description="版本选择: v1(实时计算), v3(优化版，推荐)")
):
    """导出累计投料量（按天，仅带料仓的回转窑）
    
    **功能说明**:
    - 统计带料仓的回转窑的投料记录
    - 按天汇总：当日投料总量
    - 数据来源：feeding_records measurement
    - **仅包含**: 7个带料仓的回转窑（no_hopper_1和no_hopper_2无料仓）
    
    **设备列表**:
    - short_hopper_1~4: 窑7,6,5,4
    - long_hopper_1~3: 窑8,3,9
    
    **时间参数**:
    - 方式1: 指定 start_time 和 end_time（ISO 8601格式）
    - 方式2: 使用 days 参数查询最近N天（默认7天）
    
    **返回结构**:
    ```json
    {
        "success": true,
        "data": {
            "hoppers": [
                {
                    "device_id": "short_hopper_1",
                    "daily_records": [
                        {
                            "date": "2026-01-26",
                            "start_time": "2026-01-26T00:00:00Z",
                            "end_time": "2026-01-26T23:59:59Z",
                            "feeding_amount": 1234.56
                        },
                        ...
                    ]
                },
                ...
            ]
        }
    }
    ```
    
    **示例**:
    ```
    # 查询最近7天
    GET /api/export/feeding-amount
    
    # 查询最近30天
    GET /api/export/feeding-amount?days=30
    
    # 查询指定时间段
    GET /api/export/feeding-amount?start_time=2026-01-01T00:00:00Z&end_time=2026-01-31T23:59:59Z
    ```
    """
    try:
        # 解析时间参数
        if start_time and end_time:
            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        else:
            end_dt = datetime.now(timezone.utc)
            start_dt = end_dt - timedelta(days=days)
        
        # 选择服务版本
        if version == "v3":
            # V3: 优化版（使用预计算数据）
            service = get_export_service_v3()
            result = service.export_feeding_v3(
                start_time=start_dt,
                end_time=end_dt
            )
        else:
            # V1: 实时计算
            service = get_export_service()
            result = service.calculate_feeding_amount_by_day(
                start_time=start_dt,
                end_time=end_dt
            )
        
        return ApiResponse.ok(result)
    
    except ValueError as e:
        return ApiResponse.fail(f"参数错误: {str(e)}")
    except Exception as e:
        return ApiResponse.fail(f"查询失败: {str(e)}")


# ============================================================
# 4. GET /api/export/electricity/all - 所有设备电量统计（按天）
# ============================================================
@router.get("/electricity/all")
async def export_all_electricity_consumption(
    start_time: Optional[str] = Query(None, description="开始时间 (ISO 8601格式)"),
    end_time: Optional[str] = Query(None, description="结束时间 (ISO 8601格式)"),
    days: Optional[int] = Query(7, description="查询最近N天（如果未指定start_time和end_time）"),
    version: Optional[str] = Query("v3", description="版本选择: v1(实时计算), v3(优化版，推荐)")
):
    """导出所有设备电量统计（按天，含运行时长，除燃气表外全部设备）
    
    **功能说明**:
    - 统计所有设备（除燃气表外）的电量消耗和运行时长
    - 按天返回：起始读数、截止读数、当日消耗、运行时长
    - 一次性获取所有设备数据
    
    **设备列表**:
    - 9个回转窑（料仓）
    - 6个辊道窑分区 + 1个辊道窑合计
    - 2个SCR氨水泵
    - 2个风机
    - **总计**: 20个设备
    - **不包含**: scr_1, scr_2（燃气表）
    
    **时间参数**:
    - 方式1: 指定 start_time 和 end_time（ISO 8601格式）
    - 方式2: 使用 days 参数查询最近N天（默认7天）
    
    **返回结构**:
    ```json
    {
        "success": true,
        "data": {
            "start_time": "2026-01-26T00:00:00Z",
            "end_time": "2026-01-28T23:59:59Z",
            "hoppers": [
                {
                    "device_id": "short_hopper_1",
                    "device_type": "hopper",
                    "total_days": 3,
                    "daily_records": [
                        {
                            "day": 1,
                            "date": "2026-01-26",
                            "start_time": "2026-01-26T00:00:00Z",
                            "end_time": "2026-01-26T23:59:59Z",
                            "start_reading": 1234.56,
                            "end_reading": 1456.78,
                            "consumption": 222.22,
                            "runtime_hours": 18.50
                        },
                        ...
                    ]
                },
                ...
            ],
            "roller_kiln_zones": [...],  # 6个分区
            "roller_kiln_total": {...},  # 合计
            "scr_devices": [...],        # 2个氨水泵
            "fan_devices": [...]         # 2个风机
        }
    }
    ```
    
    **示例**:
    ```
    # 查询最近7天所有设备
    GET /api/export/electricity/all
    
    # 查询最近30天所有设备
    GET /api/export/electricity/all?days=30
    
    # 查询指定时间段所有设备
    GET /api/export/electricity/all?start_time=2026-01-01T00:00:00Z&end_time=2026-01-31T23:59:59Z
    ```
    """
    try:
        # 解析时间参数
        if start_time and end_time:
            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        else:
            end_dt = datetime.now(timezone.utc)
            start_dt = end_dt - timedelta(days=days)
        
        # 选择服务版本
        if version == "v3":
            # V3: 优化版（使用预计算数据）
            service = get_export_service_v3()
            result = service.export_electricity_v3(
                start_time=start_dt,
                end_time=end_dt
            )
        else:
            # V1: 实时计算
            service = get_export_service()
            result = service.calculate_all_devices_electricity_by_day(
                start_time=start_dt,
                end_time=end_dt
            )
        
        return ApiResponse.ok(result)
    
    except ValueError as e:
        return ApiResponse.fail(f"参数错误: {str(e)}")
    except Exception as e:
        return ApiResponse.fail(f"查询失败: {str(e)}")


# ============================================================
# 5. GET /api/export/comprehensive - 综合导出所有数据（按天）
# ============================================================
@router.get("/comprehensive")
async def export_comprehensive_data(
    start_time: Optional[str] = Query(None, description="开始时间 (ISO 8601格式)"),
    end_time: Optional[str] = Query(None, description="结束时间 (ISO 8601格式)"),
    days: Optional[int] = Query(None, description="查询最近N天（如果未指定start_time和end_time）"),
    version: Optional[str] = Query("v3", description="版本选择: v1(旧版), v2(优化版), v3(终极优化版，推荐)")
):
    """综合导出所有设备的所有数据（按天统计）
    
    **功能说明**:
    - 整合所有设备的所有数据：电量、运行时长、燃气消耗、投料量
    - 一次性获取所有设备的完整数据
    - 适用于生成综合报表
    
    **设备列表**:
    - 9个回转窑（料仓）: 电量 + 运行时长 + 投料量
    - 6个辊道窑分区: 电量 + 运行时长
    - 1个辊道窑合计: 电量 + 运行时长（平均值）
    - 2个SCR燃气表: 燃气消耗 + 运行时长
    - 2个SCR氨水泵: 电量 + 运行时长
    - 2个风机: 电量 + 运行时长
    - **总计**: 22个设备
    
    **时间参数**:
    - 方式1: 指定 start_time 和 end_time（ISO 8601格式）
    - 方式2: 使用 days 参数查询最近N天
      - days=1: 今天0点到现在
      - days=2: 昨天0点到今天现在
      - days=N: N-1天前0点到今天现在
    - **建议**: 最多查询30天，避免查询时间过长
    
    **版本选择**:
    - **v3 (终极优化版，推荐)**:
      - 批量查询预计算数据（一次查询所有设备）
      - 并行计算不完整天（线程池）
      - 内存缓存完整天数据
      - **性能提升**: 10-20倍
      - **适用场景**: 生产环境，30天以内数据
    
    - **v2 (优化版)**:
      - 使用预计算数据
      - 串行查询（每个设备单独查询）
      - **性能提升**: 2-3倍
      - **适用场景**: 7天以内数据
    
    - **v1 (旧版)**:
      - 实时计算所有数据
      - 速度慢，仅用于调试
      - **适用场景**: 调试、验证数据准确性
    
    **返回结构**:
    ```json
    {
        "success": true,
        "data": {
            "start_time": "2026-01-26T00:00:00Z",
            "end_time": "2026-01-28T23:59:59Z",
            "total_devices": 22,
            "devices": [
                {
                    "device_id": "short_hopper_1",
                    "device_type": "hopper",
                    "daily_records": [
                        {
                            "date": "2026-01-26",
                            "start_time": "2026-01-26T00:00:00Z",
                            "end_time": "2026-01-26T23:59:59Z",
                            "gas_consumption": 0.0,           # m³ (仅SCR有)
                            "feeding_amount": 123.45,         # kg (仅料仓有)
                            "electricity_consumption": 500.5, # kWh
                            "runtime_hours": 18.5             # h
                        },
                        ...
                    ]
                },
                ...
            ]
        }
    }
    ```
    
    **数据说明**:
    - `gas_consumption`: 燃气消耗（m³），仅SCR设备有值，其他设备为0
    - `feeding_amount`: 投料量（kg），仅料仓有值，其他设备为0
    - `electricity_consumption`: 电量消耗（kWh），所有设备都有
    - `runtime_hours`: 运行时长（小时），所有设备都有
    
    **示例**:
    ```
    # 查询今天的数据（V3终极优化版，推荐）
    GET /api/export/comprehensive?days=1
    
    # 查询最近7天所有数据（V3终极优化版）
    GET /api/export/comprehensive?days=7&version=v3
    
    # 查询最近30天所有数据（V3终极优化版）
    GET /api/export/comprehensive?days=30&version=v3
    
    # 查询指定时间段所有数据（V3终极优化版）
    GET /api/export/comprehensive?start_time=2026-01-01T00:00:00Z&end_time=2026-01-31T23:59:59Z&version=v3
    
    # 使用V2版本（优化版）
    GET /api/export/comprehensive?days=7&version=v2
    
    # 使用V1版本（旧版，慢）
    GET /api/export/comprehensive?days=7&version=v1
    ```
    
    **性能对比**:
    | 版本 | 30天查询时间 | 适用场景 |
    |-----|------------|---------|
    | V3  | 1-2秒      | 生产环境（推荐） |
    | V2  | 10-15秒    | 小数据量 |
    | V1  | 60-120秒   | 调试验证 |
    """
    try:
        # 解析时间参数
        if start_time and end_time:
            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        elif days is not None:
            # 使用 days 参数（按自然日切分）
            start_dt, end_dt = parse_days_parameter(days)
        else:
            # 默认查询最近7天
            start_dt, end_dt = parse_days_parameter(7)
        
        # 限制查询天数（最多30天）
        time_diff = end_dt - start_dt
        if time_diff.days > 30:
            return ApiResponse.fail("查询时间范围不能超过30天，请缩小时间范围")
        
        # 选择服务版本
        if version == "v3":
            # V3: 终极优化版（批量查询 + 并行计算 + 内存缓存）
            service = get_export_service_v3()
            result = service.export_comprehensive_v3(
                start_time=start_dt,
                end_time=end_dt
            )
        elif version == "v2":
            # V2: 优化版（预计算数据）
            service = get_export_service_v2()
            result = service.export_comprehensive_optimized(
                start_time=start_dt,
                end_time=end_dt
            )
        else:
            # V1: 旧版（实时计算）
            service = get_export_service()
            result = service.calculate_all_data_comprehensive(
                start_time=start_dt,
                end_time=end_dt
            )
        
        return ApiResponse.ok(result)
    
    except ValueError as e:
        return ApiResponse.fail(f"参数错误: {str(e)}")
    except Exception as e:
        return ApiResponse.fail(f"查询失败: {str(e)}")
