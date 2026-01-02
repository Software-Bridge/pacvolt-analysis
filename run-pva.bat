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

REM Get current directory and user home directory
set CURRENT_DIR=%CD%
set USER_HOME=%USERPROFILE%

REM Function to convert Windows path to Docker format
REM Current directory conversion
set DRIVE_LETTER=%CURRENT_DIR:~0,1%
set DRIVE_LETTER_LOWER=%DRIVE_LETTER%
REM Convert to lowercase (basic approach)
if /I "%DRIVE_LETTER%"=="A" set DRIVE_LETTER_LOWER=a
if /I "%DRIVE_LETTER%"=="B" set DRIVE_LETTER_LOWER=b
if /I "%DRIVE_LETTER%"=="C" set DRIVE_LETTER_LOWER=c
if /I "%DRIVE_LETTER%"=="D" set DRIVE_LETTER_LOWER=d
if /I "%DRIVE_LETTER%"=="E" set DRIVE_LETTER_LOWER=e
if /I "%DRIVE_LETTER%"=="F" set DRIVE_LETTER_LOWER=f
if /I "%DRIVE_LETTER%"=="G" set DRIVE_LETTER_LOWER=g
if /I "%DRIVE_LETTER%"=="Z" set DRIVE_LETTER_LOWER=z

REM Convert current directory to Docker path
set DOCKER_CURRENT_DIR=/%DRIVE_LETTER_LOWER%%CURRENT_DIR:~2%
set DOCKER_CURRENT_DIR=%DOCKER_CURRENT_DIR:\=/%

REM User home directory conversion
set HOME_DRIVE_LETTER=%USER_HOME:~0,1%
set HOME_DRIVE_LOWER=%HOME_DRIVE_LETTER%
if /I "%HOME_DRIVE_LETTER%"=="A" set HOME_DRIVE_LOWER=a
if /I "%HOME_DRIVE_LETTER%"=="B" set HOME_DRIVE_LOWER=b
if /I "%HOME_DRIVE_LETTER%"=="C" set HOME_DRIVE_LOWER=c
if /I "%HOME_DRIVE_LETTER%"=="D" set HOME_DRIVE_LOWER=d
if /I "%HOME_DRIVE_LETTER%"=="E" set HOME_DRIVE_LOWER=e
if /I "%HOME_DRIVE_LETTER%"=="F" set HOME_DRIVE_LOWER=f
if /I "%HOME_DRIVE_LETTER%"=="G" set HOME_DRIVE_LOWER=g
if /I "%HOME_DRIVE_LETTER%"=="Z" set HOME_DRIVE_LOWER=z

REM Convert user home to Docker path
set DOCKER_USER_HOME=/%HOME_DRIVE_LOWER%%USER_HOME:~2%
set DOCKER_USER_HOME=%DOCKER_USER_HOME:\=/%

echo Starting container...
echo Mounting: %USER_HOME% -^> /home/user
echo Mounting: %CURRENT_DIR% -^> /workspace

REM Run the container
REM - Mount user home directory for data access
REM - Mount current directory as working directory
REM - Map port 8081 (host) to 5000 (container) for web interface
REM - Remove container after exit
REM - Pass all arguments through
docker run --rm ^
    --name pva-container ^
    -v "%USER_HOME%:/home/user" ^
    -v "%CURRENT_DIR%:/workspace" ^
    -w /workspace ^
    -p 8081:5000 ^
    pva-app %*

echo.
echo ==============================
echo Container finished
echo ==============================
pause
