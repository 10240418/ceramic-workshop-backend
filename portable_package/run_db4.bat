@echo off
chcp 65001 >nul
"%~dp0python\python.exe" "%~dp0parse_db4_hopper_sensors.py"
pause
