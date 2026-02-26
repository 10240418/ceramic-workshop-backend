@echo off
chcp 65001 >nul
"%~dp0..\python\python.exe" "%~dp0parse_db7_roller_status.py"
pause

