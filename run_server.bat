@echo off
echo Starting Agentic Honey-Pot API...
echo.

REM Check if port is in use
netstat -ano | findstr :8000 > nul
if %errorlevel% equ 0 (
    echo Port 8000 is already in use!
    echo Killing processes on port 8000...
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000') do taskkill /PID %%a /F
    timeout /t 2 /nobreak > nul
)

REM Activate virtual environment
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else (
    echo Creating virtual environment...
    python -m venv venv
    call venv\Scripts\activate.bat
    pip install fastapi uvicorn pydantic python-dotenv
)

echo.
echo Starting API server...
echo.
echo API will be available at: http://localhost:8000
echo API Docs: http://localhost:8000/docs
echo Health Check: http://localhost:8000/health
echo.
echo Press Ctrl+C to stop the server
echo.

python simple_honeypot.py
pause