# ============================================================
# 配置管理工具 - 可视化管理 PLC 映射配置
# ============================================================
# 功能:
# 1. 查看当前配置
# 2. 添加新字段
# 3. 修改偏移量
# 4. 修改缩放因子
# 5. 启用/禁用分组
# ============================================================

import yaml
from pathlib import Path
from typing import Dict, Any, List

class PLCConfigManager:
    """PLC 配置管理器"""
    
    def __init__(self, config_path: str = "configs/plc_mapping.yaml"):
        self.config_path = Path(config_path)
        self.load_config()
    
    def load_config(self):
        """加载配置文件"""
        with open(self.config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
    
    def save_config(self):
        """保存配置文件"""
        with open(self.config_path, 'w', encoding='utf-8') as f:
            yaml.dump(self.config, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
        print(f"✅ 配置已保存到: {self.config_path}")
    
    def list_dbs(self) -> List[Dict[str, Any]]:
        """列出所有 DB 块"""
        dbs = []
        for key, config in self.config.items():
            if isinstance(config, dict) and 'db_number' in config:
                dbs.append({
                    'key': key,
                    'db_number': config['db_number'],
                    'description': config.get('description', ''),
                    'enabled': config.get('enabled', True)
                })
        return dbs
    
    def list_fields(self, db_key: str, group_name: str = None) -> List[Dict[str, Any]]:
        """列出指定 DB 块的所有字段"""
        if db_key not in self.config:
            raise ValueError(f"未找到 DB 块: {db_key}")
        
        db_config = self.config[db_key]
        all_fields = []
        
        for gname, gconfig in db_config.items():
            if gname in ['db_number', 'description', 'total_size', 'enabled']:
                continue
            
            if group_name and gname != group_name:
                continue
            
            for field in gconfig.get('fields', []):
                all_fields.append({
                    'group': gname,
                    **field
                })
        
        return all_fields
    
    def update_offset(self, db_key: str, group_name: str, field_name: str, new_offset: int):
        """修改字段偏移量"""
        fields = self.config[db_key][group_name]['fields']
        for field in fields:
            if field['name'] == field_name:
                old_offset = field['offset']
                field['offset'] = new_offset
                print(f"✅ 已修改 {field_name} 的偏移量: {old_offset} → {new_offset}")
                return
        raise ValueError(f"未找到字段: {field_name}")
    
    def update_scale(self, db_key: str, group_name: str, field_name: str, new_scale: float):
        """修改缩放因子"""
        fields = self.config[db_key][group_name]['fields']
        for field in fields:
            if field['name'] == field_name:
                old_scale = field.get('scale', 1)
                field['scale'] = new_scale
                print(f"✅ 已修改 {field_name} 的缩放因子: {old_scale} → {new_scale}")
                return
        raise ValueError(f"未找到字段: {field_name}")
    
    def add_field(self, db_key: str, group_name: str, field_config: Dict[str, Any]):
        """添加新字段"""
        if 'fields' not in self.config[db_key][group_name]:
            self.config[db_key][group_name]['fields'] = []
        
        self.config[db_key][group_name]['fields'].append(field_config)
        print(f"✅ 已添加字段: {field_config['name']}")
    
    def toggle_group(self, db_key: str, group_name: str):
        """切换分组启用状态"""
        current = self.config[db_key][group_name].get('enabled', True)
        self.config[db_key][group_name]['enabled'] = not current
        status = "启用" if not current else "禁用"
        print(f"✅ 已{status}分组: {group_name}")


# ============================================================
# 命令行交互界面
# ============================================================
def main():
    manager = PLCConfigManager()
    
    while True:
        print("\n" + "=" * 70)
        print("PLC 配置管理工具")
        print("=" * 70)
        print("1. 查看所有 DB 块")
        print("2. 查看 DB 块字段")
        print("3. 修改字段偏移量")
        print("4. 修改缩放因子")
        print("5. 添加新字段")
        print("6. 启用/禁用分组")
        print("7. 保存配置")
        print("0. 退出")
        print("=" * 70)
        
        choice = input("\n请选择操作 (0-7): ").strip()
        
        if choice == '0':
            print("👋 再见!")
            break
        
        elif choice == '1':
            print("\n📋 所有 DB 块:")
            for db in manager.list_dbs():
                status = "✅ 启用" if db['enabled'] else "❌ 禁用"
                print(f"  [{db['key']}] DB{db['db_number']}: {db['description']} - {status}")
        
        elif choice == '2':
            db_key = input("输入 DB 块 key (如 db6_slave_data): ").strip()
            try:
                fields = manager.list_fields(db_key)
                print(f"\n📋 DB 块字段 ({len(fields)} 个):")
                for field in fields:
                    print(f"  [{field['group']}] {field['name']}")
                    print(f"    显示名: {field['display_name']}")
                    print(f"    偏移量: {field['offset']}")
                    print(f"    类型: {field['data_type']}")
                    print(f"    单位: {field['unit']}")
                    print(f"    缩放: {field.get('scale', 1)}\n")
            except Exception as e:
                print(f"❌ 错误: {e}")
        
        elif choice == '3':
            db_key = input("DB 块 key: ").strip()
            group = input("分组名: ").strip()
            field = input("字段名: ").strip()
            offset = int(input("新偏移量: ").strip())
            try:
                manager.update_offset(db_key, group, field, offset)
            except Exception as e:
                print(f"❌ 错误: {e}")
        
        elif choice == '4':
            db_key = input("DB 块 key: ").strip()
            group = input("分组名: ").strip()
            field = input("字段名: ").strip()
            scale = float(input("新缩放因子: ").strip())
            try:
                manager.update_scale(db_key, group, field, scale)
            except Exception as e:
                print(f"❌ 错误: {e}")
        
        elif choice == '5':
            print("\n添加新字段:")
            db_key = input("DB 块 key: ").strip()
            group = input("分组名: ").strip()
            
            field_config = {
                'name': input("字段名 (英文): ").strip(),
                'display_name': input("显示名 (中文): ").strip(),
                'offset': int(input("偏移量: ").strip()),
                'data_type': input("数据类型 (WORD/DWORD/REAL/INT 等): ").strip(),
                'unit': input("单位: ").strip(),
                'scale': float(input("缩放因子 (默认 1): ").strip() or "1")
            }
            
            try:
                manager.add_field(db_key, group, field_config)
            except Exception as e:
                print(f"❌ 错误: {e}")
        
        elif choice == '6':
            db_key = input("DB 块 key: ").strip()
            group = input("分组名: ").strip()
            try:
                manager.toggle_group(db_key, group)
            except Exception as e:
                print(f"❌ 错误: {e}")
        
        elif choice == '7':
            manager.save_config()
        
        else:
            print("❌ 无效选择")


if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════════════╗
║                    PLC 配置管理工具 v1.0                         ║
╚══════════════════════════════════════════════════════════════════╝

💡 使用说明:
  - 配置文件: configs/plc_mapping.yaml
  - 修改配置后记得保存 (选项 7)
  - 也可以直接编辑 YAML 文件
    """)
    
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 已退出")
