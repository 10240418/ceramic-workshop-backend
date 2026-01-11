# ============================================================
# 流量计转换器 (FlowMeter)
# ============================================================
# 存储字段: flow_rate (L/min), total_flow (m³)
# 
# 🔧 2026-01-10 更新:
#   - flow_rate 单位改为 L/min（原 m³/h）
#   - total_flow 保持 m³ 不变
# ============================================================

from typing import Dict, Any
from .converter_base import BaseConverter


class FlowConverter(BaseConverter):
    """
    气体流量计数据转换器
    
    输入字段 (PLC原始):
        - RtFlow: 实时流量 (原始值，需要 × 0.001 转换为 L/min)
        - TotalFlow: 累计流量整数部分 (m³, DWord)
        - TotalFlowMilli: 累计流量小数部分 (mL, Word)
    
    输出字段 (存储):
        - flow_rate: 实时流量 (L/min)
        - total_flow: 累计流量 (m³)
    
    转换公式:
        flow_rate = RtFlow × 0.001 (原始值 → L/min)
        total_flow = TotalFlow + TotalFlowMilli / 1000.0
    """
    
    MODULE_TYPE = "FlowMeter"
    
    # 缩放系数
    SCALE_FLOW_RATE = 0.001  # 原始值 × 0.001 = L/min
    
    OUTPUT_FIELDS = {
        "flow_rate": {"display_name": "实时流量", "unit": "L/min"},
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
        rt_flow_raw = self.get_field_value(raw_data, "RtFlow", 0)
        total_flow_m3 = self.get_field_value(raw_data, "TotalFlow", 0)  # m³ 整数
        total_flow_ml = self.get_field_value(raw_data, "TotalFlowMilli", 0)  # mL 小数
        
        # 🔧 实时流量: 原始值 × 0.001 = L/min
        # 例如: raw=42223 → 42.223 L/min
        flow_rate = rt_flow_raw * self.SCALE_FLOW_RATE
        
        # 累计流量: 整数部分 + 小数部分
        total_flow = total_flow_m3 + total_flow_ml / 1000.0
        
        return {
            "flow_rate": round(flow_rate, 2),
            "total_flow": round(total_flow, 3),
        }
