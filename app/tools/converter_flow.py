# ============================================================
# 流量计转换器 (FlowMeter)
# ============================================================
# 存储字段: flow_rate (m³/h), total_flow (m³)
# ============================================================

from typing import Dict, Any
from .converter_base import BaseConverter


class FlowConverter(BaseConverter):
    """
    气体流量计数据转换器
    
    输入字段 (PLC原始):
        - RtFlow: 实时流量 (L/min, DWord)
        - TotalFlow: 累计流量整数部分 (m³, DWord)
        - TotalFlowMilli: 累计流量小数部分 (mL, Word)
    
    输出字段 (存储):
        - flow_rate: 实时流量 (m³/h)
        - total_flow: 累计流量 (m³)
    
    转换公式:
        flow_rate = RtFlow / 1000 * 60  (L/min → m³/h)
        total_flow = TotalFlow + TotalFlowMilli / 1000.0
    """
    
    MODULE_TYPE = "FlowMeter"
    
    OUTPUT_FIELDS = {
        "flow_rate": {"display_name": "实时流量", "unit": "m³/h"},
        "total_flow": {"display_name": "累计流量", "unit": "m³"},
    }
    
    def convert(self, raw_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """
        转换流量计数据
        
        Args:
            raw_data: Parser 解析后的原始数据
        
        Returns:
            存储字段字典
        """
        # 获取原始值
        rt_flow_lpm = self.get_field_value(raw_data, "RtFlow", 0)  # L/min
        total_flow_m3 = self.get_field_value(raw_data, "TotalFlow", 0)  # m³ 整数
        total_flow_ml = self.get_field_value(raw_data, "TotalFlowMilli", 0)  # mL 小数
        
        # 转换计算
        # 实时流量: L/min → m³/h
        # 1 L = 0.001 m³, 1 min = 1/60 h
        # flow_rate = rt_flow * 0.001 * 60 = rt_flow * 0.06
        flow_rate = rt_flow_lpm * 0.06
        
        # 累计流量: 整数部分 + 小数部分
        total_flow = total_flow_m3 + total_flow_ml / 1000.0
        
        return {
            "flow_rate": round(flow_rate, 4),
            "total_flow": round(total_flow, 3),
        }
