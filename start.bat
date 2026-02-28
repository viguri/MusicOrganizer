@echo off
REM Script para iniciar frontend y backend de MusicOrganizer en Windows

echo.
echo [94m=== Iniciando MusicOrganizer ===[0m
echo.

REM Obtener el directorio del script
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

REM Verificar si existe el entorno virtual
if not exist ".venv\Scripts\activate.bat" (
    echo [93mCreando entorno virtual...[0m
    python -m venv .venv
    echo [92mEntorno virtual creado[0m
)

REM Activar entorno virtual
call .venv\Scripts\activate.bat

REM Verificar e instalar dependencias del backend
echo [94mVerificando dependencias del backend...[0m
python -c "import fastapi" 2>nul
if errorlevel 1 (
    echo [93mInstalando dependencias del backend...[0m
    pip install -r backend\requirements.txt
    echo [92mDependencias del backend instaladas[0m
)

REM Verificar e instalar dependencias del frontend
if not exist "frontend\node_modules" (
    echo [93mInstalando dependencias del frontend...[0m
    cd frontend
    call npm install
    cd ..
    echo [92mDependencias del frontend instaladas[0m
)

REM Crear archivo temporal para almacenar PIDs
set PID_FILE=%TEMP%\musicorganizer_pids.txt
if exist "%PID_FILE%" del "%PID_FILE%"

echo.
echo [92m=== Iniciando servicios ===[0m
echo.

REM Iniciar backend en una nueva ventana
echo [96mIniciando backend (Python/FastAPI)...[0m
start "MusicOrganizer Backend" /MIN cmd /c "cd /d "%SCRIPT_DIR%" && .venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000"
timeout /t 3 /nobreak >nul

REM Iniciar frontend en una nueva ventana
echo [96mIniciando frontend (React/Vite)...[0m
start "MusicOrganizer Frontend" /MIN cmd /c "cd /d "%SCRIPT_DIR%\frontend" && npm run dev"
timeout /t 2 /nobreak >nul

echo.
echo [92m=== Servicios iniciados ===[0m
echo.
echo   - Backend:  http://127.0.0.1:8000
echo   - Frontend: http://localhost:5173
echo   - Rekordbox: http://localhost:5173/rekordbox.html
echo.
echo [93mLos servicios se estan ejecutando en ventanas separadas (minimizadas)[0m
echo [93mCierra las ventanas o presiona Ctrl+C en ellas para detener los servicios[0m
echo.
echo [96mPresiona cualquier tecla para abrir el navegador...[0m
pause >nul

REM Abrir navegador
start http://localhost:5173

echo.
echo [92mNavegador abierto. Los servicios continuan ejecutandose.[0m
echo [93mCierra las ventanas de Backend y Frontend para detener los servicios.[0m
echo.
