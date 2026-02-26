@echo off
chcp 65001 >nul
"%~dp0..\python\python.exe" "%~dp0parse_db10_scr_fans.py"
pause

