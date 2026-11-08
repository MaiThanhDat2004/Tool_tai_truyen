@echo off
title Tool Tai Truyen Pro
cd /d "%~dp0"

:: Tim Python trong moi truong ao .venv
set "PY="
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PY=%~dp0.venv\Scripts\python.exe"
)

:: Neu khong co trong .venv, tim tren PATH he thong
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)

if not defined PY (
    echo ======================================================================
    echo [LOI] Khong tim thay Python!
    echo Vui long kiem tra lai thu muc .venv hoac cai dat Python tren may.
    echo ======================================================================
    pause
    exit /b 1
)

:: Khoi dong giao dien
"%PY%" "%~dp0gui.py"

if errorlevel 1 (
    echo.
    echo ======================================================================
    echo [LOI] Giao dien bi dong dot ngot hoac gap su co! (Ma loi: %errorlevel%)
    echo Hay kiem tra thong bao loi o tren hoac xem file gui_crash.log (neu co).
    echo ======================================================================
    pause
)
