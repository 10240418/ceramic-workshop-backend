#!/usr/bin/env python3
"""修复SCR燃气表的运行时长计算"""

# 读取文件
with open('/app/app/services/data_export_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 查找并替换SCR燃气表的处理逻辑
old_code = '''        # 4.3 处理SCR燃气表 - 只有燃气消耗数据（scr_1, scr_2）
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

new_code = '''        # 4.3 处理SCR燃气表 - 有燃气消耗和运行时长（scr_1, scr_2）
        scr_gas_ids = ["scr_1", "scr_2"]
        for scr_id in scr_gas_ids:
            # 查找对应的燃气消耗数据
            gas_records_map = {}
            if scr_id in gas_data:
                for record in gas_data[scr_id]["daily_records"]:
                    gas_records_map[record["date"]] = record["consumption"]
            
            # 构建每日记录（有燃气消耗和运行时长）
            daily_records = []
            
            # 按天分割时间段
            current_date = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
            while current_date < end_time:
                date = current_date.strftime("%Y-%m-%d")
                day_start = max(current_date, start_time)
                day_end = min(current_date + timedelta(days=1) - timedelta(seconds=1), end_time)
                
                # 计算运行时长（基于燃气流量 > 0.01 m³/h）
                runtime_hours = self._calculate_gas_meter_runtime(
                    scr_id, day_start, day_end
                )
                
                daily_records.append({
                    "date": date,
                    "start_time": self._format_timestamp(day_start),
                    "end_time": self._format_timestamp(day_end),
                    "gas_consumption": gas_records_map.get(date, 0.0),
                    "feeding_amount": 0.0,
                    "electricity_consumption": 0.0,  # 燃气表没有电量数据
                    "runtime_hours": runtime_hours  # 根据燃气流量计算运行时长
                })
                
                current_date += timedelta(days=1)
            
            devices.append({
                "device_id": scr_id,
                "device_type": "scr_gas_meter",
                "daily_records": daily_records
            })'''

content = content.replace(old_code, new_code)

# 在 _calculate_runtime_for_period 方法之后添加新方法
marker = '''    def _calculate_runtime_for_period(
        self,
        device_id: str,
        start_time: datetime,
        end_time: datetime,
        module_tag: Optional[str] = None
    ) -> float:
        """计算指定时间段内的运行时长
        
        Args:
            device_id: 设备ID
            start_time: 开始时间
            end_time: 结束时间
            module_tag: 模块标签（可选，用于辊道窑分区和SCR燃气表）
            
        Returns:
            运行时长（小时）
        """
        # 构建查询条件
        module_filter = ""
        if module_tag:
            module_filter = f'|> filter(fn: (r) => r["module_tag"] == "{module_tag}")'
        
        query = f\'\'\'
        from(bucket: "{self.bucket}")
            |> range(start: {start_time.isoformat()}, stop: {end_time.isoformat()})
            |> filter(fn: (r) => r["_measurement"] == "sensor_data")
            |> filter(fn: (r) => r["device_id"] == "{device_id}")
            {module_filter}
            |> filter(fn: (r) => r["_field"] == "Pt")
            |> filter(fn: (r) => r["_value"] > {self.power_threshold})
            |> count()
        \'\'\'
        
        try:
            result = self.query_api.query(query)
            running_points = 0
            
            for table in result:
                for record in table.records:
                    running_points = record.get_value()
                    break
            
            # 计算运行时间（假设数据采集间隔为6秒）
            polling_interval_seconds = 6
            runtime_seconds = running_points * polling_interval_seconds
            runtime_hours = round(runtime_seconds / 3600, 2)
            
            print(f"🔍 计算运行时长: device_id={device_id}, module_tag={module_tag}, points={running_points}, hours={runtime_hours}")
            
            return runtime_hours
        except Exception as e:
            print(f"⚠️  计算 {device_id} 运行时长失败: {str(e)}")
            return 0.0'''

new_method = '''
    
    def _calculate_gas_meter_runtime(
        self,
        device_id: str,
        start_time: datetime,
        end_time: datetime
    ) -> float:
        """计算SCR燃气表的运行时长（基于燃气流量）
        
        Args:
            device_id: 设备ID（scr_1 或 scr_2）
            start_time: 开始时间
            end_time: 结束时间
            
        Returns:
            运行时长（小时）
        """
        # 查询燃气流量数据，流量 > 0.01 m³/h 表示运行中
        query = f\'\'\'
        from(bucket: "{self.bucket}")
            |> range(start: {start_time.isoformat()}, stop: {end_time.isoformat()})
            |> filter(fn: (r) => r["_measurement"] == "sensor_data")
            |> filter(fn: (r) => r["device_id"] == "{device_id}")
            |> filter(fn: (r) => r["module_tag"] == "gas_meter")
            |> filter(fn: (r) => r["_field"] == "flow_rate")
            |> filter(fn: (r) => r["_value"] > 0.01)
            |> count()
        \'\'\'
        
        try:
            result = self.query_api.query(query)
            running_points = 0
            
            for table in result:
                for record in table.records:
                    running_points = record.get_value()
                    break
            
            # 计算运行时间（假设数据采集间隔为6秒）
            polling_interval_seconds = 6
            runtime_seconds = running_points * polling_interval_seconds
            runtime_hours = round(runtime_seconds / 3600, 2)
            
            print(f"🔍 计算燃气表运行时长: device_id={device_id}, points={running_points}, hours={runtime_hours}")
            
            return runtime_hours
        except Exception as e:
            print(f"⚠️  计算 {device_id} 燃气表运行时长失败: {str(e)}")
            return 0.0'''

# 在 _calculate_runtime_for_period 方法之后插入新方法
content = content.replace(marker, marker + new_method)

# 写回文件
with open('/app/app/services/data_export_service.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ 已修复SCR燃气表的运行时长计算")
print("✅ 现在SCR燃气表会根据燃气流量（flow_rate > 0.01 m³/h）计算运行时长")

