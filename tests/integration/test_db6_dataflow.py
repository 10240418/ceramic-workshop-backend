"""
PLC DB6 原始数据读取测试
读取料仓数据块并输出十六进制格式
"""
import snap7

# PLC 配置
IP = "192.168.50.223"
RACK = 0
SLOT = 1
DB_NUMBER = 6
READ_LENGTH = 82  # DB6 总长度

def test_read_db6():
    """读取 DB6 原始数据"""
    print("=" * 70)
    print("PLC DB6 (料仓) 原始数据读取")
    print("=" * 70)
    print(f"连接: {IP}, Rack={RACK}, Slot={SLOT}")
    print(f"读取: DB{DB_NUMBER}, 0-{READ_LENGTH-1} 字节")
    print("=" * 70)
    
    client = snap7.client.Client()
    
    try:
        # 连接 PLC
        client.connect(IP, RACK, SLOT)
        
        if not client.get_connected():
            print("❌ PLC 连接失败")
            return
            
        print("✅ PLC 连接成功!")
        
        # 读取 DB6 数据
        data = client.db_read(DB_NUMBER, 0, READ_LENGTH)
        
        print(f"\n原始数据 ({len(data)} 字节):")
        print("=" * 70)
        
        # 按 16 字节一行显示
        for i in range(0, len(data), 16):
            chunk = data[i:i+16]
            hex_str = ' '.join(f'{b:02X}' for b in chunk)
            offset_str = f"[{i:4d}]"
            print(f"{offset_str} {hex_str}")
        
        print("=" * 70)
        print(f"✅ DB6 数据读取完成! 共 {len(data)} 字节")
        
    except Exception as e:
        print(f"❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        if client.get_connected():
            client.disconnect()
            print("🔌 连接已关闭")

if __name__ == "__main__":
    test_read_db6()
