# ============================================================
# 文件说明: parser_status.py - 设备通信状态解析器
# ============================================================
# 功能:
#   - 解析 PLC 中的设备通信状态位
#   - 检测电表、温度、流量、称重传感器的通信状态
#   - 仅在通信失败时记录日志
# ============================================================

import struct
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime


class StatusParser:
    """设备通信状态解析器"""
    
    def __init__(self, config_path: str = "configs/config_status.yaml"):
        """初始化状态解析器
        
        Args:
            config_path: 状态配置文件路径
        """
        self.config = self._load_config(config_path)
        self._last_error_states: Dict[str, bool] = {}  # 上次错误状态，避免重复日志
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """加载状态配置文件"""
        path = Path(config_path)
        if not path.exists():
            print(f"⚠️ 状态配置文件不存在: {config_path}")
            return {}
        
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def parse_device_status(self, data: bytes, offset: int, module_type: str = "DeviceStatus") -> Dict[str, Any]:
        """解析单个设备的状态
        
        Args:
            data: DB块数据
            offset: 设备状态的起始偏移量
            module_type: 模块类型 (DeviceStatus 或 CommLoadStatus)
        
        Returns:
            {
                "done": bool,
                "busy": bool,  # CommLoadStatus 没有 busy
                "error": bool,
                "status_code": int
            }
        """
        if offset + 4 > len(data):
            return {"done": False, "busy": False, "error": True, "status_code": -1}
        
        # 读取第一个字节 (包含 DONE, BUSY, ERROR 位)
        status_byte = data[offset]
        
        # 解析布尔位
        done = bool(status_byte & 0x01)   # bit 0
        
        if module_type == "CommLoadStatus":
            # MB_COMM_LOAD: DONE(bit0), ERROR(bit1), STATUS(offset+2)
            busy = False
            error = bool(status_byte & 0x02)  # bit 1
        else:
            # DeviceStatus: DONE(bit0), BUSY(bit1), ERROR(bit2), STATUS(offset+2)
            busy = bool(status_byte & 0x02)   # bit 1
            error = bool(status_byte & 0x04)  # bit 2
        
        # 读取状态码 (Word, 2 bytes, Big Endian)
        status_code = struct.unpack('>H', data[offset + 2:offset + 4])[0]
        
        return {
            "done": done,
            "busy": busy,
            "error": error,
            "status_code": status_code
        }
    
    def check_all_status(self, status_data: bytes) -> Tuple[List[Dict], List[Dict]]:
        """检查所有设备状态
        
        Args:
            status_data: 状态 DB 块的原始数据
        
        Returns:
            (success_list, error_list): 成功设备列表和失败设备列表
        """
        success_list = []
        error_list = []
        
        # 获取设备列表 (新格式: devices 列表)
        devices = self.config.get('devices', [])
        
        for device in devices:
            device_id = device.get('device_id', '')
            offset = device.get('offset', 0)
            module_type = device.get('module_type', 'DeviceStatus')
            description = device.get('description', device_id)
            
            # 根据 device_id 判断设备类型
            if 'ELEC' in device_id:
                device_type = 'electricity_meter'
            elif 'THERMAL' in device_id:
                device_type = 'temperature_sensor'
            elif 'FLOW' in device_id:
                device_type = 'flow_meter'
            elif 'WEIGH' in device_id:
                device_type = 'weight_sensor'
            elif 'COMM_LOAD' in device_id:
                device_type = 'comm_load'
            else:
                device_type = 'unknown'
            
            status = self.parse_device_status(status_data, offset, module_type)
            
            result = {
                "device_id": device_id,
                "device_type": device_type,
                "description": description,
                "offset": offset,
                **status
            }
            
            if status['error']:
                error_list.append(result)
            else:
                success_list.append(result)
        
        return success_list, error_list
    
    def log_errors_only(self, status_data: bytes) -> int:
        """仅记录错误状态的设备（成功不记录，恢复也不记录）
        
        Args:
            status_data: 状态 DB 块的原始数据
        
        Returns:
            错误设备数量
        """
        success_list, error_list = self.check_all_status(status_data)
        
        # 只有出现新的错误时才记录日志
        for error in error_list:
            device_id = error['device_id']
            
            # 检查是否是新出现的错误（避免重复日志）
            if not self._last_error_states.get(device_id, False):
                desc = error.get('description', '')
                # 简化日志输出
                print(f"❌ 状态位: {desc if desc else device_id} 通信失败")
            
            # 更新错误状态
            self._last_error_states[device_id] = True
        
        # 静默清除已恢复的设备的错误状态（不输出日志）
        success_ids = {s['device_id'] for s in success_list}
        for device_id in list(self._last_error_states.keys()):
            if device_id in success_ids:
                self._last_error_states[device_id] = False
        
        return len(error_list)
    
    def get_status_summary(self, status_data: bytes) -> Dict[str, Any]:
        """获取状态摘要
        
        Args:
            status_data: 状态 DB 块的原始数据
        
        Returns:
            {
                "total": 总设备数,
                "success": 成功数,
                "error": 错误数,
                "error_devices": [错误设备列表]
            }
        """
        success_list, error_list = self.check_all_status(status_data)
        
        return {
            "total": len(success_list) + len(error_list),
            "success": len(success_list),
            "error": len(error_list),
            "error_devices": error_list
        }


# 单例实例
_status_parser: Optional[StatusParser] = None


def get_status_parser() -> StatusParser:
    """获取状态解析器单例"""
    global _status_parser
    if _status_parser is None:
        _status_parser = StatusParser()
    return _status_parser
