@echo off
chcp 65001 >nul
"%~dp0python\python.exe" "%~dp0parse_db2_sensor_data.py"
pause
