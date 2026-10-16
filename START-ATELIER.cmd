@echo off
cd /d "%~dp0"
py -3 launch_seller.py --storefront
if errorlevel 1 pause
