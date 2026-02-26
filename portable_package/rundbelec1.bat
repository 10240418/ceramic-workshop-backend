@echo off
chcp 65001 >nul
echo === DB1 变频器/弧流弧压数据 ===
"%~dp0python\python.exe" "%~dp0parser_elec_db1.py"
pause

