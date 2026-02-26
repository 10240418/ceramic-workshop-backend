@echo off
chcp 65001 >nul
"%~dp0..\python\python.exe" "%~dp0parse_db3_hopper_status.py"
pause

