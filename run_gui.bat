@echo off
cd /d "%~dp0"
set "PYW=%~dp0.venv\Scripts\pythonw.exe"
if not exist "%PYW%" set "PYW=pythonw"
start "" "%PYW%" "%~dp0gui.py"
