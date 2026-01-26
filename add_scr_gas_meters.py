#!/usr/bin/env python3
"""在4.4节之前插入4.3节：处理SCR燃气表"""

# 读取文件
with open('/app/app/services/data_export_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 要插入的4.3节代码
section_43 = '''        
        # 4.3 处理SCR燃气表 - 只有燃气消耗数据（scr_1, scr_2）
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
            })
        
'''

# 在 "# 4.4 处理SCR氨水泵" 之前插入
marker = "        # 4.4 处理SCR氨水泵 - 只有电量和运行时长"
content = content.replace(marker, section_43 + marker)

# 写回文件
with open('/app/app/services/data_export_service.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ 已在4.4节之前插入4.3节：处理SCR燃气表")
print("✅ 现在综合导出应该返回22个设备：")
print("   - 9个回转窑")
print("   - 6个辊道窑分区 + 1个辊道窑合计")
print("   - 2个SCR燃气表（scr_1, scr_2）")
print("   - 2个SCR氨水泵（scr_1_pump, scr_2_pump）")
print("   - 2个风机")

