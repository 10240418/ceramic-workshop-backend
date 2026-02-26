@echo off
chcp 65001 >nul
echo === DB1 主站状态 ===
"%~dp0python\python.exe" "%~dp0parse_db1_master_status.py"
echo.
echo === DB2 传感器数据 ===
"%~dp0python\python.exe" "%~dp0parse_db2_sensor_data.py"
echo.
echo === DB3 从站状态 ===
"%~dp0python\python.exe" "%~dp0parse_db3_slave_status.py"
pause
