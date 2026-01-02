@echo off
REM Launcher script for PacVolt Analysis on Windows PC
REM Runs pva.py in a Docker container with all arguments passed through

echo ==============================
echo PacVolt Analysis Docker Launcher
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
docker build -f Dockerfile.pva -t pva-app .

if errorlevel 1 (
    echo Error: Failed to build Docker image
    pause
    exit /b 1
)

REM Stop any existing container
docker stop pva-container 2>nul
docker rm pva-container 2>nul

REM Get current directory
set CURRENT_DIR=%CD%

REM Convert Windows drive letter to Docker format (C:\ -> /c/)
set DRIVE_LETTER=%CURRENT_DIR:~0,1%
set DRIVE_LETTER_LOWER=%DRIVE_LETTER%
REM Convert to lowercase (basic approach)
if "%DRIVE_LETTER%"=="C" set DRIVE_LETTER_LOWER=c
if "%DRIVE_LETTER%"=="D" set DRIVE_LETTER_LOWER=d
if "%DRIVE_LETTER%"=="E" set DRIVE_LETTER_LOWER=e

REM Convert current directory to Docker path
set DOCKER_CURRENT_DIR=/%DRIVE_LETTER_LOWER%%CURRENT_DIR:~2%
REM Replace backslashes with forward slashes
set DOCKER_CURRENT_DIR=%DOCKER_CURRENT_DIR:\=/%

echo Starting container...
echo Mounting: %CURRENT_DIR% -^> /workspace

REM Run the container
REM - Mount current directory as working directory
REM - Map port 8081 (host) to 5000 (container) for web interface
REM - Remove container after exit
REM - Pass all arguments through
docker run --rm ^
    --name pva-container ^
    -v "%CURRENT_DIR%:/workspace" ^
    -w /workspace ^
    -p 8081:5000 ^
    pva-app %*

echo.
echo ==============================
echo Container finished
echo ==============================
pause
