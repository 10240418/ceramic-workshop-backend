# ============================================================
# 数据转换工具模块
# ============================================================
# 用于将 PLC 原始数据转换为 InfluxDB 存储字段
#
# 模块列表:
#   - converter_base: 转换器基类
#   - converter_elec: 电表数据转换
#   - converter_flow: 流量计数据转换
#   - converter_temp: 温度传感器数据转换
#   - converter_weight: 称重传感器数据转换
#
# 存储字段定义见: CONVERTER_FIELDS.md
# ============================================================

from .converter_base import BaseConverter
from .converter_elec import ElectricityConverter
from .converter_flow import FlowConverter
from .converter_temp import TemperatureConverter
from .converter_weight import WeightConverter

# 模块类型 → 转换器类 映射
CONVERTER_MAP = {
    "ElectricityMeter": ElectricityConverter,
    "FlowMeter": FlowConverter,
    "TemperatureSensor": TemperatureConverter,
    "WeighSensor": WeightConverter,
}


def get_converter(module_type: str) -> BaseConverter:
    """
    根据模块类型获取对应的转换器实例
    
    Args:
        module_type: 模块类型名称
    
    Returns:
        转换器实例
    
    Raises:
        ValueError: 未知的模块类型
    """
    if module_type not in CONVERTER_MAP:
        raise ValueError(f"未知的模块类型: {module_type}")
    return CONVERTER_MAP[module_type]()


__all__ = [
    'BaseConverter',
    'ElectricityConverter',
    'FlowConverter',
    'TemperatureConverter',
    'WeightConverter',
    'CONVERTER_MAP',
    'get_converter',
]
