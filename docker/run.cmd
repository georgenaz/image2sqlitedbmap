@echo off
setlocal enabledelayedexpansion

REM Run image2sqlitedbmap in a Docker container.
REM Usage: run.cmd <map_file> [options]
REM   run.cmd C:\maps\map.map
REM   run.cmd C:\maps\map.map -f mbtiles -o output.mbtiles
REM   run.cmd C:\maps\map.map -q

set "SCRIPT_DIR=%~dp0"
set "PROJECT_DIR=%SCRIPT_DIR%.."
set "IMAGE_NAME=image2sqlitedbmap"

REM Build image if it doesn't exist
docker image inspect %IMAGE_NAME% >nul 2>&1
if errorlevel 1 (
    echo Building Docker image '%IMAGE_NAME%'...
    docker build -t %IMAGE_NAME% -f "%SCRIPT_DIR%Dockerfile" "%PROJECT_DIR%"
    if errorlevel 1 (
        echo ERROR: Failed to build Docker image.
        exit /b 1
    )
)

REM Need at least the .map file path
if "%~1"=="" (
    echo Usage: %~nx0 ^<map_file^> [options]
    echo.
    echo Options are passed to the application, see: python main.py --help
    exit /b 1
)

REM Get directory and filename of the map file
set "MAP_NAME=%~nx1"
set "MAP_DIR=%~dp1"

REM Convert backslashes to forward slashes for Docker volume mount, strip trailing slash
set "MAP_DIR=%MAP_DIR:\=/%"
set "MAP_DIR=%MAP_DIR:~0,-1%"

REM Shift first argument, collect the rest
shift
set "ARGS="
:loop
if "%~1"=="" goto endloop
set "ARGS=%ARGS% %~1"
shift
goto loop
:endloop

docker run --rm -it -v "%MAP_DIR%:/data" -w /data %IMAGE_NAME% "/data/%MAP_NAME%"%ARGS%

endlocal
