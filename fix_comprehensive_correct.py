#!/usr/bin/env python3
"""正确修复综合导出：包含SCR燃气表，排除SCR氨水泵"""

import re

# 读取文件
with open('/app/app/services/data_export_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 查找 4.3 节和 4.4 节
# 需要：
# 1. 修改 4.3 节：正确处理 SCR 燃气表（从 gas_data 获取，而不是 electricity_data["scr_devices"]）
# 2. 删除 4.4 节：删除 SCR 氨水泵的处理

# 先删除 4.3 和 4.4 节
pattern = r'        # 4\.3 处理SCR设备.*?(?=        # 4\.5 处理风机)'
new_content = re.sub(pattern, '', content, flags=re.DOTALL)

# 在 4.5 节之前插入正确的 4.3 节（处理 SCR 燃气表）
scr_gas_section = '''        # 4.3 处理SCR燃气表 - 只有燃气消耗（没有电量数据）
        for scr_id in ["scr_1", "scr_2"]:
            # 查找对应的燃气消耗数据
            gas_records_map = {}
            if scr_id in gas_data:
                for record in gas_data[scr_id]["daily_records"]:
                    gas_records_map[record["date"]] = record["consumption"]
            
            # 整合每日记录（只有燃气消耗，电量和运行时长为0）
            daily_records = []
            
            # 获取日期列表（从燃气数据）
            if scr_id in gas_data:
                for gas_record in gas_data[scr_id]["daily_records"]:
                    daily_records.append({
                        "date": gas_record["date"],
                        "start_time": gas_record["start_time"],
                        "end_time": gas_record["end_time"],
                        "gas_consumption": gas_record["consumption"],
                        "feeding_amount": 0.0,  # SCR没有投料
                        "electricity_consumption": 0.0,  # 燃气表不耗电
                        "runtime_hours": 0.0  # 燃气表没有运行时长概念
                    })
            
            devices.append({
                "device_id": scr_id,
                "device_type": "scr_gas_meter",
                "daily_records": daily_records
            })
        
'''

# 在 "# 4.5 处理风机" 之前插入
new_content = new_content.replace('        # 4.5 处理风机', scr_gas_section + '        # 4.5 处理风机')

# 写回文件
with open('/app/app/services/data_export_service.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print("✅ 已修复综合导出：")
print("   - 添加了 SCR 燃气表（scr_1, scr_2）- 只有燃气消耗数据")
print("   - 删除了 SCR 氨水泵（scr_1_pump, scr_2_pump）")
print("✅ 现在综合导出应该返回20个设备：")
print("   - 9个回转窑 + 6个辊道窑分区 + 1个辊道窑合计 + 2个SCR燃气表 + 2个风机 = 20")

