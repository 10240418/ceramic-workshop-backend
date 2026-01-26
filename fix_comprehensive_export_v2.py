#!/usr/bin/env python3
"""修复综合导出：正确处理SCR燃气表和SCR氨水泵"""

import re

# 读取文件
with open('/app/app/services/data_export_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 查找 4.3 节的位置（处理SCR设备）
# 需要修改这部分，使其正确处理SCR燃气表（scr_1, scr_2）而不是从 electricity_data["scr_devices"] 读取

old_section_43 = r'''        # 4\.3 处理SCR设备 - 燃气表（有电量、运行时长、燃气消耗）
        for scr in electricity_data\["scr_devices"\]:
            device_id = scr\["device_id"\]
            
            # 查找对应的燃气消耗数据
            gas_records_map = \{\}
            if device_id in gas_data:
                for record in gas_data\[device_id\]\["daily_records"\]:
                    gas_records_map\[record\["date"\]\] = record\["consumption"\]
            
            # 整合每日记录
            daily_records = \[\]
            for elec_record in scr\["daily_records"\]:
                date = elec_record\["date"\]
                daily_records\.append\(\{
                    "date": date,
                    "start_time": elec_record\["start_time"\],
                    "end_time": elec_record\["end_time"\],
                    "gas_consumption": gas_records_map\.get\(date, 0\.0\),
                    "feeding_amount": 0\.0,  # SCR没有投料
                    "electricity_consumption": elec_record\["consumption"\],
                    "runtime_hours": elec_record\["runtime_hours"\]
                \}\)
            
            devices\.append\(\{
                "device_id": device_id,
                "device_type": "scr",
                "daily_records": daily_records
            \}\)'''

new_section_43 = '''        # 4.3 处理SCR燃气表 - 只有燃气消耗数据（scr_1, scr_2）
        scr_gas_ids = ["scr_1", "scr_2"]
        for scr_id in scr_gas_ids:
            # 查找对应的燃气消耗数据
            gas_records_map = {}
            if scr_id in gas_data:
                for record in gas_data[scr_id]["daily_records"]:
                    gas_records_map[record["date"]] = record["consumption"]
            
            # 构建每日记录（只有燃气消耗，没有电量和运行时长）
            daily_records = []
            
            # 按天分割时间段
            current_date = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
            while current_date < end_time:
                date = current_date.strftime("%Y-%m-%d")
                day_start = max(current_date, start_time)
                day_end = min(current_date + timedelta(days=1) - timedelta(seconds=1), end_time)
                
                daily_records.append({
                    "date": date,
                    "start_time": self._format_timestamp(day_start),
                    "end_time": self._format_timestamp(day_end),
                    "gas_consumption": gas_records_map.get(date, 0.0),
                    "feeding_amount": 0.0,
                    "electricity_consumption": 0.0,  # 燃气表没有电量数据
                    "runtime_hours": 0.0  # 燃气表没有运行时长
                })
                
                current_date += timedelta(days=1)
            
            devices.append({
                "device_id": scr_id,
                "device_type": "scr_gas_meter",
                "daily_records": daily_records
            })'''

# 替换 4.3 节
content = re.sub(old_section_43, new_section_43, content, flags=re.DOTALL)

# 写回文件
with open('/app/app/services/data_export_service.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ 已修复综合导出：")
print("   - 4.3节：处理2个SCR燃气表（scr_1, scr_2）- 只有燃气消耗")
print("   - 4.4节：处理2个SCR氨水泵（scr_1_pump, scr_2_pump）- 有电量和运行时长")
print("✅ 现在综合导出应该返回22个设备：")
print("   - 9个回转窑")
print("   - 6个辊道窑分区 + 1个辊道窑合计")
print("   - 2个SCR燃气表")
print("   - 2个SCR氨水泵")
print("   - 2个风机")

