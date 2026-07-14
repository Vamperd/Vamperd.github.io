@echo off
cd /d "%~dp0.."
where py >nul 2>nul
if %errorlevel% equ 0 (
  py -3 todo_app\server.py
) else (
  python todo_app\server.py
)
if %errorlevel% neq 0 pause
