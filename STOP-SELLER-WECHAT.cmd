@echo off
setlocal
cd /d "%~dp0"
if not exist ".seller-agent-runtime" mkdir ".seller-agent-runtime"
type nul > ".seller-agent-runtime\stop-8780"
echo Stop requested. Business data is preserved.
