@echo off
REM =====================================================================
REM detect-motion Windows Runner
REM Runs detect-motion in a Docker container with mounted video folders
REM =====================================================================

REM Usage:
REM   run-detect-motion.bat [INPUT_FOLDER] [OUTPUT_FOLDER] [DROP_FOLDER] [DETECT_MOTION_ARGS...]
REM
REM Only INPUT_FOLDER is required. OUTPUT_FOLDER and DROP_FOLDER default to
REM "<input>-keep" and "<input>-drop" next to the input folder.
REM
REM This runner also adds --move and --progress by default; pass --quiet to
REM suppress the progress output, or --copy to copy kept videos instead of
REM moving them (runner-only flag, not forwarded to detect-motion).
REM
REM Examples:
REM   run-detect-motion.bat "C:\Videos"
REM   run-detect-motion.bat "C:\Videos" --profile balanced
REM   run-detect-motion.bat "C:\Videos" --dry-run
REM   run-detect-motion.bat "C:\Videos" --copy

setlocal enabledelayedexpansion

REM Default input path (relative to script location)
set "SCRIPT_DIR=%~dp0"
set "DEFAULT_INPUT=%SCRIPT_DIR%videos"

REM Image name
set "IMAGE_NAME=detect-motion:latest"

REM Parse arguments: the first three non-flag arguments are the input, output
REM and drop folders; everything else is passed to detect-motion.
set "INPUT_FOLDER="
set "OUTPUT_FOLDER="
set "DROP_FOLDER="
set "DETECT_ARGS="
set "ARG_COUNT=0"
set "NEEDS_VALUE="
set "HAS_MOVE="
set "HAS_PROGRESS="
set "HAS_QUIET="

:parse_args
if "%~1"=="" goto :parse_done
if defined NEEDS_VALUE goto :arg_value
set "ARG=%~1"
if "!ARG:~0,1!"=="-" goto :arg_flag
if !ARG_COUNT! EQU 0 goto :arg_input
if !ARG_COUNT! EQU 1 goto :arg_output
if !ARG_COUNT! EQU 2 goto :arg_drop
goto :arg_extra

:arg_flag
if /i "%~1"=="--copy" goto :arg_copy
set "DETECT_ARGS=!DETECT_ARGS! "%~1""
set "NEEDS_VALUE="
echo %~1|findstr /x /c:"--input-dir" /c:"--output-dir" /c:"--drop-dir" /c:"--profile" /c:"--method" /c:"--width" /c:"--frame-stride" /c:"--min-area-ratio" /c:"--exclude" /c:"--report" /c:"--workers" >nul && set "NEEDS_VALUE=1"
if /i "%~1"=="--move" set "HAS_MOVE=1"
if /i "%~1"=="--progress" set "HAS_PROGRESS=1"
if /i "%~1"=="-p" set "HAS_PROGRESS=1"
if /i "%~1"=="--quiet" set "HAS_QUIET=1"
shift
goto :parse_args

:arg_copy
REM Runner-only flag: suppress the default --move, copy kept videos instead
set "HAS_MOVE=1"
shift
goto :parse_args

:arg_value
set "DETECT_ARGS=!DETECT_ARGS! "%~1""
set "NEEDS_VALUE="
shift
goto :parse_args

:arg_input
set "INPUT_FOLDER=%~f1"
set /a ARG_COUNT+=1
shift
goto :parse_args

:arg_output
set "OUTPUT_FOLDER=%~f1"
set /a ARG_COUNT+=1
shift
goto :parse_args

:arg_drop
set "DROP_FOLDER=%~f1"
set /a ARG_COUNT+=1
shift
goto :parse_args

:arg_extra
set "DETECT_ARGS=!DETECT_ARGS! "%~1""
shift
goto :parse_args

:parse_done

REM Only the input folder is required. Derive the other two from it, e.g.
REM C:\video
REM   -> C:\video-keep
REM   -> C:\video-drop
if "!INPUT_FOLDER!"=="" set "INPUT_FOLDER=%DEFAULT_INPUT%"

REM Drop a trailing backslash so the folder name can be derived (keep drive roots)
if not "!INPUT_FOLDER:~3!"=="" if "!INPUT_FOLDER:~-1!"=="\" set "INPUT_FOLDER=!INPUT_FOLDER:~0,-1!"

for %%I in ("!INPUT_FOLDER!") do (
    set "INPUT_PARENT=%%~dpI"
    set "INPUT_NAME=%%~nxI"
)
if "!OUTPUT_FOLDER!"=="" set "OUTPUT_FOLDER=!INPUT_PARENT!!INPUT_NAME!-keep"
if "!DROP_FOLDER!"=="" set "DROP_FOLDER=!INPUT_PARENT!!INPUT_NAME!-drop"

REM Pass the Windows paths through unchanged. Docker Desktop accepts
REM drive-letter paths (E:\Videos); rewriting them to /e/Videos would point
REM at a non-existent path inside the Docker VM and mount an empty folder.
set "DOCKER_INPUT=!INPUT_FOLDER!"
set "DOCKER_OUTPUT=!OUTPUT_FOLDER!"
set "DOCKER_DROP=!DROP_FOLDER!"

REM Create host directories if they don't exist
if not exist "!INPUT_FOLDER!" mkdir "!INPUT_FOLDER!" 2>nul
if not exist "!OUTPUT_FOLDER!" mkdir "!OUTPUT_FOLDER!" 2>nul
if not exist "!DROP_FOLDER!" mkdir "!DROP_FOLDER!" 2>nul

REM Build docker run command
set "DOCKER_CMD=docker run --rm "
set "DOCKER_CMD=!DOCKER_CMD!-v "!DOCKER_INPUT!:/data/video" "
set "DOCKER_CMD=!DOCKER_CMD!-v "!DOCKER_OUTPUT!:/data/keep" "
set "DOCKER_CMD=!DOCKER_CMD!-v "!DOCKER_DROP!:/data/drop" "
set "DOCKER_CMD=!DOCKER_CMD!%IMAGE_NAME% "

REM Add default input/output dirs if not overridden by user args
echo !DETECT_ARGS! | find "--input-dir" >nul 2>&1
if errorlevel 1 set "DOCKER_CMD=!DOCKER_CMD! --input-dir /data/video"

echo !DETECT_ARGS! | find "--output-dir" >nul 2>&1
if errorlevel 1 set "DOCKER_CMD=!DOCKER_CMD! --output-dir /data/keep"

REM Keep the drop folder consistent with the derived host folder
echo !DETECT_ARGS! | find "--drop-dir" >nul 2>&1
if errorlevel 1 set "DOCKER_CMD=!DOCKER_CMD! --drop-dir /data/drop"

REM Keep the JSON report on the host: the default would land in the container's
REM working directory and be discarded with --rm.
echo !DETECT_ARGS! | find "--report" >nul 2>&1
if errorlevel 1 set "DOCKER_CMD=!DOCKER_CMD! --report /data/keep/motion-report.json"

REM Runner defaults: move instead of copy, and show progress
if not defined HAS_MOVE set "DOCKER_CMD=!DOCKER_CMD! --move"
if not defined HAS_PROGRESS if not defined HAS_QUIET set "DOCKER_CMD=!DOCKER_CMD! --progress"

REM Append user arguments
set "DOCKER_CMD=!DOCKER_CMD! !DETECT_ARGS!"

REM Show what we're doing
echo.
echo =====================================================================
echo Starting detect-motion container
echo =====================================================================
echo Input folder:    !INPUT_FOLDER!
echo Output folder:   !OUTPUT_FOLDER!
echo Drop folder:     !DROP_FOLDER!
echo Docker command:  !DOCKER_CMD!
echo =====================================================================
echo.

REM Execute
!DOCKER_CMD!

endlocal
goto :eof
