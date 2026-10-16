@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
if exist "..\runtime\venv\Scripts\python.exe" (
  "..\runtime\venv\Scripts\python.exe" launch_seller.py --phone %*
) else (
  python launch_seller.py --phone %*
)
if errorlevel 1 pause
