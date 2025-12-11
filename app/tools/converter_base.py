# ============================================================
# 转换器基类
# ============================================================
# 定义所有模块转换器的基础接口
# ============================================================

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class BaseConverter(ABC):
    """
    转换器基类
    
    所有模块转换器必须继承此类并实现 convert() 方法
    """
    
    # 模块类型名称 (子类必须定义)
    MODULE_TYPE: str = ""
    
    # 输出字段定义 (子类必须定义)
    # 格式: {"字段名": {"display_name": "显示名", "unit": "单位"}}
    OUTPUT_FIELDS: Dict[str, Dict[str, str]] = {}
    
    def __init__(self):
        """初始化转换器"""
        pass
    
    @abstractmethod
    def convert(self, raw_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """
        将 PLC 原始数据转换为存储字段
        
        Args:
            raw_data: Parser 解析后的原始字段数据
                      格式: {"field_name": {"value": xxx, "data_type": "Real", ...}, ...}
            **kwargs: 额外参数 (如历史数据等)
        
        Returns:
            转换后的字段字典，直接用于 InfluxDB 存储
            格式: {"field_name": value, ...}
        """
        pass
    
    def get_field_value(self, raw_data: Dict[str, Any], field_name: str, 
                        default: Any = 0.0) -> Any:
        """
        安全获取原始字段值
        
        Args:
            raw_data: 原始数据字典
            field_name: 字段名
            default: 默认值
        
        Returns:
            字段值或默认值
        """
        if field_name in raw_data:
            field_info = raw_data[field_name]
            if isinstance(field_info, dict):
                return field_info.get('value', default)
            return field_info
        return default
    
    @classmethod
    def get_output_field_names(cls) -> list:
        """获取输出字段名列表"""
        return list(cls.OUTPUT_FIELDS.keys())
    
    @classmethod
    def get_module_type(cls) -> str:
        """获取模块类型名称"""
        return cls.MODULE_TYPE
