@echo off
chcp 65001 >nul
"%~dp0python\python.exe" "%~dp0parse_db3_slave_status.py"
pause
