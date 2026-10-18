@echo off
setlocal
cd /d "%~dp0"
title Crear ejecutable Visor HP 35670A
if not exist ".venv\Scripts\python.exe" (
  echo Ejecuta INSTALAR.bat antes de crear el EXE.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --windowed --onedir --name Visor_HP35670A --collect-all PySide6 --collect-all matplotlib --hidden-import matplotlib.backends.backend_qtagg main.py
if errorlevel 1 (
  echo Error al crear el ejecutable.
  pause
  exit /b 1
)
echo Ejecutable generado en dist\Visor_HP35670A\Visor_HP35670A.exe
pause
