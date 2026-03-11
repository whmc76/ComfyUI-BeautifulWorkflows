@echo off
chcp 65001 >nul
cd /d "%~dp0"
title ComfyUI Workflow Beautifier

echo Starting ComfyUI Workflow Beautifier...
python gui.py

if errorlevel 1 (
    echo.
    echo [ERROR] Failed to start. Make sure Python 3.10+ is installed.
    pause
)
