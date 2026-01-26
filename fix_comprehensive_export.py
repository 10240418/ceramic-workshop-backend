#!/usr/bin/env python3
"""修复综合导出中SCR设备重复的问题"""

import re

# 读取文件
with open('/app/app/services/data_export_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 查找并删除 4.3 节（处理SCR设备 - 燃气表）
# 这部分代码错误地处理了 electricity_data["scr_devices"]，导致重复添加
pattern = r'        # 4\.3 处理SCR设备 - 燃气表.*?(?=        # 4\.4 处理SCR氨水泵)'

# 替换为空（删除4.3节）
new_content = re.sub(pattern, '', content, flags=re.DOTALL)

# 写回文件
with open('/app/app/services/data_export_service.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print("✅ 已删除4.3节（SCR燃气表处理），避免重复添加SCR氨水泵")
print("✅ 现在综合导出应该返回20个设备（9回转窑 + 6辊道窑分区 + 1辊道窑合计 + 2SCR氨水泵 + 2风机）")

