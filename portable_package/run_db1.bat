@echo off
chcp 65001 >nul
"%~dp0python\python.exe" "%~dp0parse_db1_master_status.py"
pause
