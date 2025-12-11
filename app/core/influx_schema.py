# ============================================================
# 文件说明: influx_schema.py - InfluxDB Schema 定义
# ============================================================
# 定义所有 Measurement 的结构（表结构）
# 启动时自动创建 Bucket、Retention Policy 等
# ============================================================

from typing import Dict, List, Any
from dataclasses import dataclass
from enum import Enum


class RetentionPeriod(str, Enum):
    """数据保留周期"""
    INFINITE = "0s"      # 永久保留（无限期）


@dataclass
class FieldDefinition:
    """字段定义"""
    name: str
    field_type: str      # float, integer, string, boolean
    description: str
    unit: str = ""


@dataclass
class MeasurementSchema:
    """Measurement（表）结构定义"""
    name: str                           # Measurement 名称
    description: str                    # 描述
    tags: List[str]                     # Tag 列表（索引字段）
    fields: List[FieldDefinition]       # Field 列表（数值字段）
    retention: RetentionPeriod          # 保留周期


# ============================================================
# InfluxDB Schema 定义
# ============================================================

# 辊道窑温度数据
ROLLER_KILN_TEMP_SCHEMA = MeasurementSchema(
    name="roller_kiln_temp",
    description="辊道窑温度数据",
    retention=RetentionPeriod.INFINITE,
    tags=["zone_id"],  # 温区ID作为标签
    fields=[
        FieldDefinition("temperature", "float", "当前温度", "°C"),
        FieldDefinition("set_point", "float", "设定温度", "°C"),
    ]
)

# 辊道窑能耗数据
ROLLER_KILN_ENERGY_SCHEMA = MeasurementSchema(
    name="roller_kiln_energy",
    description="辊道窑能耗数据",
    retention=RetentionPeriod.INFINITE,
    tags=[],
    fields=[
        FieldDefinition("voltage", "float", "电压", "V"),
        FieldDefinition("current", "float", "电流", "A"),
        FieldDefinition("power", "float", "功率", "kW"),
        FieldDefinition("total_energy", "float", "累计电量", "kWh"),
        FieldDefinition("status", "integer", "运行状态", ""),
    ]
)

# 回转窑温度数据
ROTARY_KILN_TEMP_SCHEMA = MeasurementSchema(
    name="rotary_kiln_temp",
    description="回转窑温度数据",
    retention=RetentionPeriod.INFINITE,
    tags=["device_id", "zone_id"],  # 设备ID和温区ID
    fields=[
        FieldDefinition("temperature", "float", "当前温度", "°C"),
        FieldDefinition("set_point", "float", "设定温度", "°C"),
    ]
)

# 回转窑能耗数据
ROTARY_KILN_ENERGY_SCHEMA = MeasurementSchema(
    name="rotary_kiln_energy",
    description="回转窑能耗数据",
    retention=RetentionPeriod.INFINITE,
    tags=["device_id"],
    fields=[
        FieldDefinition("voltage", "float", "电压", "V"),
        FieldDefinition("current", "float", "电流", "A"),
        FieldDefinition("power", "float", "功率", "kW"),
        FieldDefinition("total_energy", "float", "累计电量", "kWh"),
        FieldDefinition("status", "integer", "运行状态", ""),
    ]
)

# 回转窑下料数据
ROTARY_KILN_FEED_SCHEMA = MeasurementSchema(
    name="rotary_kiln_feed",
    description="回转窑下料数据",
    retention=RetentionPeriod.INFINITE,
    tags=["device_id"],
    fields=[
        FieldDefinition("feed_speed", "float", "下料速度", "kg/h"),
    ]
)

# 回转窑料仓数据
ROTARY_KILN_HOPPER_SCHEMA = MeasurementSchema(
    name="rotary_kiln_hopper",
    description="回转窑料仓数据",
    retention=RetentionPeriod.INFINITE,
    tags=["device_id", "hopper_id"],
    fields=[
        FieldDefinition("weight", "float", "当前重量", "kg"),
        FieldDefinition("capacity", "float", "总容量", "kg"),
        FieldDefinition("percent", "float", "容量百分比", "%"),
        FieldDefinition("low_alarm", "integer", "低重量告警", ""),
    ]
)

# SCR 风机数据
SCR_FAN_SCHEMA = MeasurementSchema(
    name="scr_fan",
    description="SCR风机数据",
    retention=RetentionPeriod.INFINITE,
    tags=["device_id", "fan_id"],
    fields=[
        FieldDefinition("power", "float", "功率", "kW"),
        FieldDefinition("cumulative_energy", "float", "累计电量", "kWh"),
        FieldDefinition("status", "integer", "运行状态", ""),
    ]
)

# SCR 氨水泵数据
SCR_PUMP_SCHEMA = MeasurementSchema(
    name="scr_pump",
    description="SCR氨水泵数据",
    retention=RetentionPeriod.INFINITE,
    tags=["device_id", "pump_id"],
    fields=[
        FieldDefinition("power", "float", "功率", "kW"),
        FieldDefinition("cumulative_energy", "float", "累计电量", "kWh"),
        FieldDefinition("status", "integer", "运行状态", ""),
    ]
)

# SCR 燃气数据
SCR_GAS_SCHEMA = MeasurementSchema(
    name="scr_gas",
    description="SCR燃气数据",
    retention=RetentionPeriod.INFINITE,
    tags=["device_id", "pipeline_id"],
    fields=[
        FieldDefinition("flow_rate", "float", "当前流速", "m³/h"),
        FieldDefinition("cumulative_volume", "float", "累计用量", "m³"),
    ]
)

# 告警记录
ALARMS_SCHEMA = MeasurementSchema(
    name="alarms",
    description="告警记录",
    retention=RetentionPeriod.INFINITE,  # 告警永久保留
    tags=["device_type", "device_id", "alarm_type", "alarm_level"],
    fields=[
        FieldDefinition("message", "string", "告警消息", ""),
        FieldDefinition("value", "float", "触发告警的值", ""),
        FieldDefinition("threshold", "float", "告警阈值", ""),
        FieldDefinition("acknowledged", "integer", "是否已确认", ""),
        FieldDefinition("resolved", "integer", "是否已解决", ""),
    ]
)

# 生产统计数据（示例：演示如何添加新表）
PRODUCTION_STATS_SCHEMA = MeasurementSchema(
    name="production_stats",
    description="生产统计数据",
    retention=RetentionPeriod.INFINITE,
    tags=["device_id", "device_type", "shift"],  # 设备ID、设备类型、班次
    fields=[
        FieldDefinition("output", "integer", "产量", "件"),
        FieldDefinition("qualified_count", "integer", "合格数", "件"),
        FieldDefinition("defect_count", "integer", "不合格数", "件"),
        FieldDefinition("qualified_rate", "float", "合格率", "%"),
        FieldDefinition("energy_consumption", "float", "能耗", "kWh"),
        FieldDefinition("runtime", "float", "运行时长", "h"),
    ]
)

# 模块化数据表 (配置驱动)
MODULE_DATA_SCHEMA = MeasurementSchema(
    name="module_data",
    description="模块化传感器数据 (配置驱动)",
    retention=RetentionPeriod.INFINITE,
    tags=[
        "device_id",       # 设备ID
        "device_type",     # 设备类型 (rotary_kiln, roller_kiln, scr)
        "module_name",     # 模块名称 (WeighSensor, FlowMeter, etc)
        "sensor_type",     # 传感器类型 (自定义标签)
    ],
    fields=[
        # 动态字段，由 ModuleParser 自动解析后写入
        # 字段名格式: {结构}__{字段名}，如 BaseWeigh_GrossWeigh
        # 所有字段均为 float 类型（数值数据）
        FieldDefinition("_placeholder", "float", "占位符（实际字段由配置生成）", ""),
    ]
)

# ============================================================
# 所有 Schema 定义（注册表）
# ============================================================
ALL_SCHEMAS: List[MeasurementSchema] = [
    # 窑炉设备
    ROLLER_KILN_TEMP_SCHEMA,
    ROLLER_KILN_ENERGY_SCHEMA,
    ROTARY_KILN_TEMP_SCHEMA,
    ROTARY_KILN_ENERGY_SCHEMA,
    ROTARY_KILN_FEED_SCHEMA,
    ROTARY_KILN_HOPPER_SCHEMA,
    
    # SCR 设备
    SCR_FAN_SCHEMA,
    SCR_PUMP_SCHEMA,
    SCR_GAS_SCHEMA,
    
    # 系统功能
    ALARMS_SCHEMA,
    PRODUCTION_STATS_SCHEMA,
    
    # 模块化数据 (新增)
    MODULE_DATA_SCHEMA,
]


def get_schema_by_name(name: str) -> MeasurementSchema:
    """根据名称获取 Schema"""
    for schema in ALL_SCHEMAS:
        if schema.name == name:
            return schema
    raise ValueError(f"Schema not found: {name}")


def list_all_measurements() -> List[str]:
    """列出所有 Measurement 名称"""
    return [schema.name for schema in ALL_SCHEMAS]


def get_schema_summary() -> Dict[str, Any]:
    """获取 Schema 摘要信息"""
    return {
        "total_measurements": len(ALL_SCHEMAS),
        "measurements": [
            {
                "name": schema.name,
                "description": schema.description,
                "tags_count": len(schema.tags),
                "fields_count": len(schema.fields),
                "retention": schema.retention.value,
            }
            for schema in ALL_SCHEMAS
        ]
    }


if __name__ == "__main__":
    print("=" * 70)
    print("InfluxDB Schema 定义")
    print("=" * 70)
    
    summary = get_schema_summary()
    print(f"\n总计 Measurements: {summary['total_measurements']}")
    
    for m in summary['measurements']:
        print(f"\n📊 {m['name']}")
        print(f"   描述: {m['description']}")
        print(f"   Tags: {m['tags_count']} 个")
        print(f"   Fields: {m['fields_count']} 个")
        print(f"   保留: {m['retention']}")
