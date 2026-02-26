@echo off
chcp 65001 >nul
"%~dp0..\python\python.exe" "%~dp0parse_db11_scr_fan_status.py"
pause

