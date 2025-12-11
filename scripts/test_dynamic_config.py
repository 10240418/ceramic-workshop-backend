#!/usr/bin/env python3
# ============================================================
# 测试动态配置加载
# ============================================================

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import yaml


def test_db_mappings():
    """测试DB映射配置加载"""
    print("=" * 60)
    print("测试 DB 映射配置")
    print("=" * 60)
    
    config_path = project_root / "configs" / "db_mappings.yaml"
    
    if not config_path.exists():
        print(f"❌ 配置文件不存在: {config_path}")
        return False
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    db_mappings = config.get('db_mappings', [])
    
    print(f"\n✅ 找到 {len(db_mappings)} 个DB块配置:\n")
    
    for mapping in db_mappings:
        status = "✅ 启用" if mapping.get('enabled', True) else "⏸️  禁用"
        print(f"{status} DB{mapping['db_number']}: {mapping['db_name']}")
        print(f"   - 配置文件: {mapping['config_file']}")
        print(f"   - 解析器: {mapping['parser_class']}")
        print(f"   - 大小: {mapping['total_size']} 字节")
        print(f"   - 说明: {mapping['description']}")
        print()
    
    # 验证配置文件是否存在
    print("\n验证配置文件是否存在:")
    for mapping in db_mappings:
        config_file = project_root / mapping['config_file']
        if config_file.exists():
            print(f"   ✅ {mapping['config_file']}")
        else:
            print(f"   ❌ {mapping['config_file']} (不存在)")
    
    return True


def test_parser_initialization():
    """测试解析器初始化"""
    print("\n" + "=" * 60)
    print("测试解析器初始化")
    print("=" * 60)
    
    try:
        from app.plc.parser_hopper import HopperParser
        from app.plc.parser_roller_kiln import RollerKilnParser
        from app.plc.parser_scr_fan import SCRFanParser
        
        parsers = {
            'HopperParser': HopperParser,
            'RollerKilnParser': RollerKilnParser,
            'SCRFanParser': SCRFanParser
        }
        
        print("\n✅ 解析器类可用:")
        for name, parser_class in parsers.items():
            print(f"   ✅ {name}")
        
        # 尝试实例化
        print("\n尝试实例化解析器:")
        instances = {}
        for name, parser_class in parsers.items():
            try:
                instance = parser_class()
                instances[name] = instance
                print(f"   ✅ {name} 实例化成功")
            except Exception as e:
                print(f"   ❌ {name} 实例化失败: {e}")
        
        return True
    
    except Exception as e:
        print(f"❌ 解析器加载失败: {e}")
        return False


def test_config_consistency():
    """测试配置一致性"""
    print("\n" + "=" * 60)
    print("测试配置一致性")
    print("=" * 60)
    
    # 加载 db_mappings.yaml
    mappings_path = project_root / "configs" / "db_mappings.yaml"
    with open(mappings_path, 'r', encoding='utf-8') as f:
        mappings = yaml.safe_load(f)
    
    all_consistent = True
    
    for mapping in mappings['db_mappings']:
        db_number = mapping['db_number']
        expected_size = mapping['total_size']
        config_file = project_root / mapping['config_file']
        
        if not config_file.exists():
            continue
        
        with open(config_file, 'r', encoding='utf-8') as f:
            device_config = yaml.safe_load(f)
        
        actual_db_number = device_config['db_config']['db_number']
        actual_size = device_config['db_config']['total_size']
        
        print(f"\n检查 {mapping['db_name']}:")
        
        # 检查 DB 号
        if actual_db_number == db_number:
            print(f"   ✅ DB号一致: DB{db_number}")
        else:
            print(f"   ❌ DB号不一致: 映射={db_number}, 配置={actual_db_number}")
            all_consistent = False
        
        # 检查大小
        if actual_size == expected_size:
            print(f"   ✅ 大小一致: {expected_size} 字节")
        else:
            print(f"   ⚠️  大小不一致: 映射={expected_size}, 配置={actual_size}")
            all_consistent = False
    
    if all_consistent:
        print("\n✅ 所有配置一致!")
    else:
        print("\n⚠️  存在配置不一致")
    
    return all_consistent


if __name__ == "__main__":
    print("\n🔍 动态配置测试\n")
    
    success = True
    success &= test_db_mappings()
    success &= test_parser_initialization()
    success &= test_config_consistency()
    
    print("\n" + "=" * 60)
    if success:
        print("✅ 所有测试通过!")
    else:
        print("❌ 部分测试失败")
    print("=" * 60)
