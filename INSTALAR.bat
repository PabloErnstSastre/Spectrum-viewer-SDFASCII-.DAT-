@echo off
setlocal
cd /d "%~dp0"
title Instalar Visor HP 35670A

echo ============================================================
echo   Instalacion del Visor HP 35670A - Pablo Ernst Sastre
echo ============================================================
echo.

if exist ".venv\Scripts\python.exe" (
  echo Entorno virtual existente detectado.
) else (
  echo Creando entorno virtual de Python...
  where py >nul 2>nul
  if %errorlevel%==0 (
    py -3.12 -m venv .venv 2>nul
    if errorlevel 1 py -3 -m venv .venv
  ) else (
    python -m venv .venv
  )
  if errorlevel 1 (
    echo ERROR: No se ha podido crear el entorno virtual. Instala Python 3.11 o 3.12 y vuelve a intentarlo.
    pause
    exit /b 1
  )
)

echo Actualizando pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto error

echo Instalando dependencias; la primera vez requiere Internet...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto error

echo.
echo Instalacion completada. Ejecuta INICIAR.bat para abrir la aplicacion.
pause
exit /b 0

:error
echo.
echo ERROR al instalar dependencias. Comprueba la conexion a Internet y la version de Python.
pause
exit /b 1
