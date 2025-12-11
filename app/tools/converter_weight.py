# ============================================================
# 称重传感器转换器 (WeighSensor)
# ============================================================
# 存储字段: weight (kg), feed_rate (kg/s)
# ============================================================

from typing import Dict, Any, Optional
from .converter_base import BaseConverter


class WeightConverter(BaseConverter):
    """
    称重传感器数据转换器
    
    输入字段 (PLC原始):
        - GrossWeight_W: 毛重 Word 精度 (不使用)
        - NetWeight_W: 净重 Word 精度 (不使用)
        - StatusWord: 状态字 (不存储)
        - GrossWeight: 毛重 DWord 高精度 (不存储)
        - NetWeight: 净重 DWord 高精度 (用于计算)
    
    输出字段 (存储):
        - weight: 实时重量 (kg)
        - feed_rate: 下料速度 (kg/s)
    
    转换公式:
        weight = NetWeight (高精度值)
        feed_rate = (previous_weight - current_weight) / interval_seconds
    
    注意:
        下料速度需要历史数据，通过 previous_weight 和 interval 参数传入
    """
    
    MODULE_TYPE = "WeighSensor"
    
    OUTPUT_FIELDS = {
        "weight": {"display_name": "实时重量", "unit": "kg"},
        "feed_rate": {"display_name": "下料速度", "unit": "kg/s"},
    }
    
    # 默认轮询间隔 (秒)
    DEFAULT_INTERVAL = 5.0
    
    def convert(self, raw_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """
        转换称重传感器数据
        
        Args:
            raw_data: Parser 解析后的原始数据
            **kwargs:
                - previous_weight: 上一次的重量值 (kg)
                - interval: 时间间隔 (秒，默认 5.0)
        
        Returns:
            存储字段字典
        """
        # 获取参数
        previous_weight: Optional[float] = kwargs.get('previous_weight')
        interval: float = kwargs.get('interval', self.DEFAULT_INTERVAL)
        
        # 获取当前重量 (优先使用高精度 DWord 值)
        current_weight = self.get_field_value(raw_data, "NetWeight", 0.0)
        
        # 如果高精度值为 0，尝试使用 Word 精度值
        if current_weight == 0:
            current_weight = self.get_field_value(raw_data, "NetWeight_W", 0.0)
        
        # 计算下料速度
        feed_rate = 0.0
        if previous_weight is not None and interval > 0:
            # 下料时重量减少: previous > current
            # feed_rate = (previous - current) / interval
            weight_diff = previous_weight - current_weight
            feed_rate = weight_diff / interval
            
            # 如果 feed_rate 为负数，说明在加料
            # 可以根据需求决定是保留负值还是设为 0
            # 这里保留负值，让上层决定如何处理
        
        return {
            "weight": round(current_weight, 2),
            "feed_rate": round(feed_rate, 4),
        }
