@echo off
REM Launcher script for Windows PC
REM Starts the Docker container and opens the browser

echo ==============================
echo Hello World Docker Launcher
echo ==============================

REM Check if Docker is running
docker info >nul 2>&1
if errorlevel 1 (
    echo Error: Docker is not running. Please start Docker Desktop.
    pause
    exit /b 1
)

REM Build the image
echo Building Docker image...
docker build -f Dockerfile.hello -t hello-world-app .

REM Stop any existing container
docker stop hello-world-container 2>nul
docker rm hello-world-container 2>nul

REM Start the container
echo Starting container...
docker run -d --name hello-world-container -p 8081:5000 hello-world-app

REM Wait for server to start
echo Waiting for server to start...
timeout /t 3 /nobreak >nul

REM Open the browser (Windows)
echo Opening browser...
start http://localhost:8081

echo.
echo ==============================
echo Application is running!
echo ==============================
echo URL: http://localhost:8081
echo.
echo To stop the application:
echo   docker stop hello-world-container
echo ==============================
pause
