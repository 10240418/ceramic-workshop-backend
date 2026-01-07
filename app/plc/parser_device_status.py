# 设备状态位解析器 - 解析 DB3/DB7/DB11 状态位
# ModuleStatus: Error(Bool, byte 0 bit 0) + Status(Word, bytes 2-3 大端序) = 4 bytes

import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional

_parser_instance: Optional["DeviceStatusParser"] = None


class DeviceStatusParser:
    """根据 YAML 配置解析 DB3/DB7/DB11 的状态位数据"""
    
    def __init__(self):
        self._configs: Dict[int, Dict[str, Any]] = {}
        for path, db in [("configs/status_hopper_3.yaml", 3),
                         ("configs/status_roller_kiln_7.yaml", 7),
                         ("configs/status_scr_fan_11.yaml", 11)]:
            if (p := Path(path)).exists():
                self._configs[db] = yaml.safe_load(p.read_text(encoding='utf-8'))
                print(f"   ✅ 加载状态配置: DB{db}")
    
    def parse_module_status(self, data: bytes, offset: int) -> Dict[str, Any]:
        """解析单个模块状态 (4字节)"""
        if offset + 4 > len(data):
            return {"error": True, "status_code": 0xFFFF, "status_hex": "FFFF"}
        error = (data[offset] & 0x01) != 0
        status_code = (data[offset + 2] << 8) | data[offset + 3]
        return {"error": error, "status_code": status_code, "status_hex": f"{status_code:04X}"}
    
    def parse_db(self, db_number: int, data: bytes, timestamp: str = None) -> List[Dict[str, Any]]:
        """解析整个 DB 块的状态数据"""
        if db_number not in self._configs:
            return []
        
        result = []
        for key, devices in self._configs[db_number].items():
            if key == 'db_config' or not isinstance(devices, list):
                continue
            for device in devices:
                # 🔧 [FIX] 兼容两种配置格式:
                # 1. 标准格式 (DB3/DB11): device 包含 modules 列表
                # 2. 扁平格式 (DB7): device 本身就是模块 (含 offset)
                
                modules = device.get('modules')
                
                # Case 1: 标准格式 (有 modules 列表)
                if modules and isinstance(modules, list):
                    for module in modules:
                        status = self.parse_module_status(data, module.get('offset', 0))
                        result.append({
                            "device_id": f"{device.get('device_id', '')}_{module.get('tag', '')}",
                            "device_name": f"{device.get('device_name', '')} - {module.get('description', '')}",
                            "device_type": device.get('device_type', ''),
                            "module_tag": module.get('tag', ''),
                            "description": module.get('description', ''),
                            "db_number": db_number,
                            "offset": module.get('offset', 0),
                            **status,
                            "is_normal": not status["error"] and status["status_code"] == 0,
                            "timestamp": timestamp
                        })
                
                # Case 2: 扁平格式 (没有 modules，自身包含 offset)
                elif 'offset' in device:
                    status = self.parse_module_status(data, device.get('offset', 0))
                    result.append({
                        "device_id": device.get('device_id', ''),
                        "device_name": device.get('device_name', ''),
                        "device_type": device.get('device_type', ''),
                        "module_tag": device.get('tag', ''),
                        "description": device.get('description', ''),
                        "db_number": db_number,
                        "offset": device.get('offset', 0),
                        **status,
                        "is_normal": not status["error"] and status["status_code"] == 0,
                        "timestamp": timestamp
                    })
        return result
    
    def parse_all(self, raw_data: Dict[str, Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """解析所有 DB 块"""
        return {key: self.parse_db(info.get('db_number'), info.get('raw_data', b''), info.get('timestamp'))
                for key, info in raw_data.items()}
    
    def get_all_as_flat_list(self, raw_data: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """解析所有 DB 块并返回扁平列表"""
        parsed = self.parse_all(raw_data)
        return [s for key in ['db3', 'db7', 'db11'] for s in parsed.get(key, [])]


def get_device_status_parser() -> DeviceStatusParser:
    """获取设备状态解析器单例"""
    global _parser_instance
    if _parser_instance is None:
        _parser_instance = DeviceStatusParser()
    return _parser_instance
