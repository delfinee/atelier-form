@echo off
setlocal
cd /d "%~dp0"
if not exist ".seller-agent-runtime" mkdir ".seller-agent-runtime"
type nul > ".seller-agent-runtime\stop-8781"
echo Stop requested for the seller phone server on port 8781.
