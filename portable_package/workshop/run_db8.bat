@echo off
chcp 65001 >nul
"%~dp0..\python\python.exe" "%~dp0parse_db8_hoppers.py"
pause

