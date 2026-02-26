# ============================================================
# 文件说明: plc_service.py - PLC通信服务 (模块化)
# ============================================================
# 方法列表:
# 1. __init__()                 - 初始化服务
# 2. read_device_data()         - 读取设备数据
# 3. _load_device_modules()     - [私有] 加载设备模块配置
# ============================================================

from typing import Dict, Any, List
from datetime import datetime
from pathlib import Path
import yaml
from app.plc.s7_client import get_s7_client
from app.plc.module_parser import ModuleParser
from config import get_settings


# ------------------------------------------------------------
# PLCService - PLC通信服务
# ------------------------------------------------------------
class PLCService:
    """PLC通信服务 (模块化，配置驱动)"""
    
    # ------------------------------------------------------------
    # 1. __init__() - 初始化服务
    # ------------------------------------------------------------
    def __init__(self):
        """初始化PLC服务"""
        self.client = get_s7_client()
        self.parser = ModuleParser()
        self.device_modules_config = None
        self._load_device_modules()
    
    # ------------------------------------------------------------
    # 3. _load_device_modules() - [私有] 加载设备模块配置
    # ------------------------------------------------------------
    def _load_device_modules(self):
        """加载设备-模块映射配置"""
        settings = get_settings()
        config_path = Path(settings.config_dir) / "device_modules.yaml"
        
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                self.device_modules_config = yaml.safe_load(f) or {}
        else:
            self.device_modules_config = {}

    def reload_config(self):
        """重新加载配置 (模块定义 + 设备映射)"""
        self.parser.load_module_configs()
        self._load_device_modules()
        print("[OK] PLCService 配置已重新加载")
    
    # ------------------------------------------------------------
    # 2. read_device_data() - 读取设备数据
    # ------------------------------------------------------------
    def read_device_data(self, device_type: str, device_id: int) -> Dict[str, Any]:
        """读取设备数据 (模块化)
        
        Args:
            device_type: 设备类型 (rotary_kiln, roller_kiln, scr, test_device)
            device_id: 设备ID
        
        Returns:
            Dict: 包含所有模块数据的字典
        """
        try:
            # 1. 查找设备配置
            device_config = self._get_device_config(device_type, device_id)
            if not device_config:
                return {
                    "timestamp": datetime.now().isoformat(),
                    "error": f"Device {device_type} #{device_id} not found"
                }
            
            # 2. 获取设备的所有模块
            module_names = [
                m['module_name'] 
                for m in device_config.get('modules', []) 
                if m.get('enabled', True)
            ]
            
            if not module_names:
                return {
                    "timestamp": datetime.now().isoformat(),
                    "error": "No enabled modules found"
                }
            
            # 3. 获取DB块编号 (从第一个模块配置中获取)
            first_module = self.parser.modules.get(module_names[0])
            if not first_module:
                return {
                    "timestamp": datetime.now().isoformat(),
                    "error": f"Module {module_names[0]} not found"
                }
            
            db_number = first_module['db_number']
            
            # 4. 计算需要读取的总字节数
            total_size = max(
                self.parser.modules[m]['start_offset'] + self.parser.modules[m]['total_size']
                for m in module_names
            )
            
            # 5. 连接PLC并读取数据
            if not self.client.is_connected():
                self.client.connect()
            
            db_data = self.client.read_db_block(db_number, 0, total_size)
            
            # 6. 解析数据
            parsed_data = self.parser.parse_device_data(module_names, db_data)
            
            # 7. 添加设备信息
            parsed_data['device_type'] = device_type
            parsed_data['device_id'] = device_id
            parsed_data['device_name'] = device_config.get('device_name', f"{device_type}_{device_id}")
            
            return parsed_data
            
        except Exception as e:
            return {
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            }
    
    # ------------------------------------------------------------
    # 4. flatten_device_data() - 扁平化设备数据 (用于写入 InfluxDB)
    # ------------------------------------------------------------
    def flatten_device_data(self, device_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """将嵌套的设备数据扁平化为 InfluxDB 数据点列表
        
        Args:
            device_data: read_device_data 返回的解析数据
            
        Returns:
            List[Dict]: InfluxDB 数据点列表
            [
                {
                    "measurement": "sensor_data",
                    "tags": {
                        "device_type": "rotary_kiln",
                        "device_id": "1",
                        "module": "WeighSensor",
                        "sensor_type": "hopper_weight"  # 来自 device_modules.yaml 的 tags
                    },
                    "fields": {
                        "BaseWeigh_GrossWeigh": 123.4,
                        "BaseWeigh_NetWeigh": 100.0,
                        "StatusWord": 1
                    },
                    "time": datetime
                }
            ]
        """
        if "error" in device_data:
            return []
            
        points = []
        timestamp = device_data.get("timestamp", datetime.now())
        device_type = device_data.get("device_type")
        device_id = str(device_data.get("device_id"))
        device_name = device_data.get("device_name")
        
        # 获取该设备的配置，以便获取模块的 tags
        device_config = self._get_device_config(device_type, int(device_id))
        module_tags_map = {}
        if device_config:
            for m in device_config.get('modules', []):
                module_tags_map[m['module_name']] = m.get('tags', {})

        # 遍历每个模块
        for module_name, module_content in device_data.get("modules", {}).items():
            # 准备基础 Tags
            tags = {
                "device_type": device_type,
                "device_id": device_id,
                "device_name": device_name,
                "module": module_name
            }
            # 合并配置文件中定义的额外 Tags (如 zone_id, sensor_type)
            if module_name in module_tags_map:
                tags.update(module_tags_map[module_name])
            
            fields = {}
            
            # 递归扁平化字段
            def _flatten_fields(prefix, data_dict):
                for key, item in data_dict.items():
                    # item 结构: {'value': ..., 'display_name': ..., 'unit': ...}
                    # 或者对于 Struct，value 可能是个字典
                    value = item.get('value')
                    
                    if isinstance(value, dict):
                        # 这是一个 Struct，递归处理
                        # 构造新的前缀，例如 "BaseWeigh"
                        new_prefix = f"{prefix}{key}_" if prefix else f"{key}_"
                        # 构造类似 fields 结构的字典来递归 (因为 parse_module 返回的结构里 value 是纯值或字典)
                        # 这里的 item['value'] 是 {'GrossWeigh': 123, ...} 这种纯值字典
                        # 但我们需要递归处理 parse_module 返回的标准结构吗？
                        # 让我们看 module_parser.py 的返回：
                        # parsed_data['fields'][field['name']] = {'value': field_value, ...}
                        # 如果 field_value 是字典 (Struct)，那么它就是 {'Child1': val1, 'Child2': val2}
                        # 所以我们需要遍历这个 value 字典
                        for sub_key, sub_val in value.items():
                            # 构造虚拟的 item 结构继续递归，或者直接处理
                            # 简单起见，直接处理值
                            full_key = f"{new_prefix}{sub_key}"
                            fields[full_key] = sub_val
                    else:
                        # 基础类型
                        full_key = f"{prefix}{key}" if prefix else key
                        # 确保 value 是 int, float, bool, str
                        if isinstance(value, (int, float, bool, str)):
                            fields[full_key] = value
            
            _flatten_fields("", module_content.get("fields", {}))
            
            if fields:
                points.append({
                    "measurement": f"{device_type}_data", # 或者统一用 sensor_data
                    "tags": tags,
                    "fields": fields,
                    "time": timestamp
                })
                
        return points

    def _get_device_config(self, device_type: str, device_id: int) -> Dict[str, Any]:
        """获取设备配置"""
        # 1. 尝试从 'mappings' 列表查找 (新版结构)
        mappings = self.device_modules_config.get('mappings', [])
        for device in mappings:
            if device.get('device_id') == device_id and device.get('device_type') == device_type:
                return device
                
        # 2. 尝试从分类键查找 (旧版结构兼容)
        device_key = f"{device_type}_modules"
        devices = self.device_modules_config.get(device_key, [])
        for device in devices:
            if device.get('device_id') == device_id and device.get('device_type') == device_type:
                return device
        
        return None
