@echo off
setlocal
cd /d "%~dp0"
title Visor HP 35670A
if not exist ".venv\Scripts\python.exe" (
  echo No se encuentra el entorno virtual.
  echo Ejecuta primero INSTALAR.bat.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" main.py
if errorlevel 1 (
  echo.
  echo La aplicacion se ha cerrado con un error. Copia el mensaje anterior para diagnosticarlo.
  pause
)
