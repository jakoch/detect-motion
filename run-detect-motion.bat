@echo off
REM =====================================================================
REM detect-motion Windows Runner
REM Runs detect-motion in a Docker container with mounted video folders
REM =====================================================================

REM Usage:
REM   run-detect-motion.bat [INPUT_FOLDER] [OUTPUT_FOLDER] [DETECT_MOTION_ARGS...]
REM
REM Examples:
REM   run-detect-motion.bat "C:\Videos" "C:\Kept"
REM   run-detect-motion.bat "C:\Videos" "C:\Kept" --profile balanced --progress
REM   run-detect-motion.bat --help

setlocal enabledelayedexpansion

REM Default paths (relative to script location)
set "SCRIPT_DIR=%~dp0"
set "DEFAULT_INPUT=%SCRIPT_DIR%videos"
set "DEFAULT_OUTPUT=%SCRIPT_DIR%videos-keep"
set "DEFAULT_QUARANTINE=%SCRIPT_DIR%videos-quarantine"

REM Image name
set "IMAGE_NAME=detect-motion:latest"

REM Parse arguments
set "INPUT_FOLDER="
set "OUTPUT_FOLDER="
set "QUARANTINE_FOLDER="
set "DETECT_ARGS="

REM First two non-flag arguments are input and output folders
set "ARG_COUNT=0"
for %%a in (%*) do (
    set "ARG=%%~a"
    if "!ARG!"=="" goto :next_arg
    
    if "!ARG:~0,1!"=="-" (
        REM It's a flag, add to detect args
        set "DETECT_ARGS=!DETECT_ARGS! "%%~a""
    ) else if !ARG_COUNT! EQU 0 (
        set "INPUT_FOLDER=%%~fa"
        set /a ARG_COUNT+=1
    ) else if !ARG_COUNT! EQU 1 (
        set "OUTPUT_FOLDER=%%~fa"
        set /a ARG_COUNT+=1
    ) else if !ARG_COUNT! EQU 2 (
        set "QUARANTINE_FOLDER=%%~fa"
        set /a ARG_COUNT+=1
    ) else (
        set "DETECT_ARGS=!DETECT_ARGS! "%%~a""
    )
    :next_arg
)

REM Use defaults if not provided
if "!INPUT_FOLDER!"=="" set "INPUT_FOLDER=%DEFAULT_INPUT%"
if "!OUTPUT_FOLDER!"=="" set "OUTPUT_FOLDER=%DEFAULT_OUTPUT%"
if "!QUARANTINE_FOLDER!"=="" set "QUARANTINE_FOLDER=%DEFAULT_QUARANTINE%"

REM Convert Windows paths to Docker-compatible paths (e.g., C:\Videos -> /c/Videos)
call :to_docker_path "!INPUT_FOLDER!" DOCKER_INPUT
call :to_docker_path "!OUTPUT_FOLDER!" DOCKER_OUTPUT
call :to_docker_path "!QUARANTINE_FOLDER!" DOCKER_QUARANTINE

REM Create host directories if they don't exist
if not exist "!INPUT_FOLDER!" mkdir "!INPUT_FOLDER!" 2>nul
if not exist "!OUTPUT_FOLDER!" mkdir "!OUTPUT_FOLDER!" 2>nul
if not exist "!QUARANTINE_FOLDER!" mkdir "!QUARANTINE_FOLDER!" 2>nul

REM Build docker run command
set "DOCKER_CMD=docker run --rm "
set "DOCKER_CMD=!DOCKER_CMD!-v "!DOCKER_INPUT!:/data/video" "
set "DOCKER_CMD=!DOCKER_CMD!-v "!DOCKER_OUTPUT!:/data/keep" "
set "DOCKER_CMD=!DOCKER_CMD!-v "!DOCKER_QUARANTINE!:/data/quarantine" "
set "DOCKER_CMD=!DOCKER_CMD!%IMAGE_NAME% "

REM Add default input/output dirs if not overridden by user args
echo !DETECT_ARGS! | find "--input-dir" >nul 2>&1
if errorlevel 1 set "DOCKER_CMD=!DOCKER_CMD! --input-dir /data/video"

echo !DETECT_ARGS! | find "--output-dir" >nul 2>&1
if errorlevel 1 set "DOCKER_CMD=!DOCKER_CMD! --output-dir /data/keep"

echo !DETECT_ARGS! | find "--quarantine-dir" >nul 2>&1
if errorlevel 1 set "DOCKER_CMD=!DOCKER_CMD! --quarantine-dir /data/quarantine"

REM Append user arguments
set "DOCKER_CMD=!DOCKER_CMD! !DETECT_ARGS!"

REM Show what we're doing
echo.
echo =====================================================================
echo Starting detect-motion container
echo =====================================================================
echo Input folder:    !INPUT_FOLDER!
echo Output folder:   !OUTPUT_FOLDER!
echo Quarantine folder: !QUARANTINE_FOLDER!
echo Docker command:  !DOCKER_CMD!
echo =====================================================================
echo.

REM Execute
!DOCKER_CMD!

endlocal
goto :eof

:to_docker_path
REM Convert Windows path to Docker-compatible path
REM Input: %1 = Windows path (e.g., C:\Videos)
REM Output: %2 = variable name to set (e.g., DOCKER_INPUT)
set "WIN_PATH=%~1"
set "DOCKER_PATH=!WIN_PATH:\=/!"
set "DOCKER_PATH=!DOCKER_PATH::=!"
set "DOCKER_PATH=/!DOCKER_PATH!"
set "%~2=!DOCKER_PATH!"
goto :eof