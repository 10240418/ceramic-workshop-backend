# ============================================================
# 文件说明: config_storage.py - YAML 配置存储管理
# ============================================================
# 方法列表:
# 1. load_config()         - 加载配置文件
# 2. save_config()         - 保存配置文件
# 3. get_config()          - 获取配置项
# 4. set_config()          - 设置配置项
# 5. get_all_devices()     - 获取所有设备配置
# 6. add_device()          - 添加设备配置
# 7. update_device()       - 更新设备配置
# 8. delete_device()       - 删除设备配置
# ============================================================

import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime


class YAMLConfigStorage:
    """YAML 配置文件存储管理
    
    用于管理设备配置、系统配置、传感器映射等
    所有配置存储在 configs/ 目录下的 YAML 文件中
    """
    
    def __init__(self, config_dir: str = "configs"):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(exist_ok=True)
        
        # 配置文件路径
        self.devices_file = self.config_dir / "devices.yaml"
        self.sensors_file = self.config_dir / "sensors.yaml"
        self.plc_mapping_file = self.config_dir / "plc_mapping.yaml"
        self.system_file = self.config_dir / "system_config.yaml"
        
        # 确保配置文件存在
        self._ensure_config_files()
    
    # ------------------------------------------------------------
    # 1. load_config() - 加载配置文件
    # ------------------------------------------------------------
    def load_config(self, filename: str) -> Dict[str, Any]:
        """加载指定的配置文件
        
        Args:
            filename: 配置文件名（如 'devices.yaml'）
            
        Returns:
            配置字典
        """
        file_path = self.config_dir / filename
        if not file_path.exists():
            return {}
        
        with open(file_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    
    # ------------------------------------------------------------
    # 2. save_config() - 保存配置文件
    # ------------------------------------------------------------
    def save_config(self, filename: str, config: Dict[str, Any]):
        """保存配置到文件
        
        Args:
            filename: 配置文件名
            config: 配置字典
        """
        file_path = self.config_dir / filename
        
        # 添加更新时间戳
        if isinstance(config, dict):
            config['_updated_at'] = datetime.now().isoformat()
        
        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
    
    # ------------------------------------------------------------
    # 3. get_config() - 获取配置项
    # ------------------------------------------------------------
    def get_config(self, category: str, key: str = None) -> Any:
        """获取配置项
        
        Args:
            category: 配置类别（如 'system', 'plc', 'influxdb'）
            key: 配置键（可选）
            
        Returns:
            配置值
        """
        config = self.load_config("system_config.yaml")
        
        if category not in config:
            return None
        
        if key is None:
            return config[category]
        
        return config[category].get(key)
    
    # ------------------------------------------------------------
    # 4. set_config() - 设置配置项
    # ------------------------------------------------------------
    def set_config(self, category: str, key: str, value: Any):
        """设置配置项
        
        Args:
            category: 配置类别
            key: 配置键
            value: 配置值
        """
        config = self.load_config("system_config.yaml")
        
        if category not in config:
            config[category] = {}
        
        config[category][key] = value
        self.save_config("system_config.yaml", config)
    
    # ------------------------------------------------------------
    # 5. get_all_devices() - 获取所有设备配置
    # ------------------------------------------------------------
    def get_all_devices(self) -> List[Dict[str, Any]]:
        """获取所有设备配置
        
        Returns:
            设备列表
        """
        config = self.load_config("devices.yaml")
        
        all_devices = []
        # 收集所有设备类型
        for device_type in ['rotary_kilns', 'roller_kilns', 'scr_equipment']:
            devices = config.get(device_type, [])
            for device in devices:
                device['device_type'] = device_type
                all_devices.append(device)
        
        return all_devices
    
    # ------------------------------------------------------------
    # 6. add_device() - 添加设备配置
    # ------------------------------------------------------------
    def add_device(self, device_type: str, device_config: Dict[str, Any]):
        """添加设备配置
        
        Args:
            device_type: 设备类型（如 'rotary_kilns'）
            device_config: 设备配置字典
        """
        config = self.load_config("devices.yaml")
        
        if device_type not in config:
            config[device_type] = []
        
        config[device_type].append(device_config)
        self.save_config("devices.yaml", config)
    
    # ------------------------------------------------------------
    # 7. update_device() - 更新设备配置
    # ------------------------------------------------------------
    def update_device(self, device_type: str, device_id: int, updates: Dict[str, Any]):
        """更新设备配置
        
        Args:
            device_type: 设备类型
            device_id: 设备ID
            updates: 更新的字段
        """
        config = self.load_config("devices.yaml")
        
        if device_type not in config:
            raise ValueError(f"设备类型不存在: {device_type}")
        
        devices = config[device_type]
        for device in devices:
            if device.get('id') == device_id:
                device.update(updates)
                break
        else:
            raise ValueError(f"设备不存在: {device_id}")
        
        self.save_config("devices.yaml", config)
    
    # ------------------------------------------------------------
    # 8. delete_device() - 删除设备配置
    # ------------------------------------------------------------
    def delete_device(self, device_type: str, device_id: int):
        """删除设备配置
        
        Args:
            device_type: 设备类型
            device_id: 设备ID
        """
        config = self.load_config("devices.yaml")
        
        if device_type not in config:
            raise ValueError(f"设备类型不存在: {device_type}")
        
        devices = config[device_type]
        config[device_type] = [d for d in devices if d.get('id') != device_id]
        
        self.save_config("devices.yaml", config)
    
    # ------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------
    def _ensure_config_files(self):
        """确保配置文件存在（创建默认配置）"""
        # 系统配置默认值
        if not self.system_file.exists():
            default_system_config = {
                'plc': {
                    'ip': '192.168.50.223',
                    'rack': 0,
                    'slot': 1,
                    'timeout': 5,
                    'poll_interval': 5
                },
                'influxdb': {
                    'url': 'http://localhost:8086',
                    'token': 'ceramic-workshop-token',
                    'org': 'ceramic-workshop',
                    'bucket': 'sensor_data'
                },
                'server': {
                    'host': '0.0.0.0',
                    'port': 8080,
                    'debug': False
                }
            }
            self.save_config("system_config.yaml", default_system_config)
    
    def get_plc_config(self) -> Dict[str, Any]:
        """获取 PLC 配置"""
        return self.get_config('plc')
    
    def get_influxdb_config(self) -> Dict[str, Any]:
        """获取 InfluxDB 配置"""
        return self.get_config('influxdb')


# 全局配置管理实例
config_storage = YAMLConfigStorage()


if __name__ == "__main__":
    print("=" * 70)
    print("YAML 配置存储测试")
    print("=" * 70)
    
    storage = YAMLConfigStorage()
    
    # 测试获取配置
    plc_config = storage.get_plc_config()
    print(f"\n PLC 配置:")
    print(f"  IP: {plc_config.get('ip')}")
    print(f"  Rack: {plc_config.get('rack')}")
    print(f"  Slot: {plc_config.get('slot')}")
    
    # 测试获取设备
    devices = storage.get_all_devices()
    print(f"\n 设备数量: {len(devices)}")
    
    print("\n[OK] 测试完成")
