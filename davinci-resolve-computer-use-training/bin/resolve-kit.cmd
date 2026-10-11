@echo off
setlocal
set "SCRIPT_DIR=%~dp0..\scripts"
set "COMMAND=%~1"
if "%COMMAND%"=="" set "COMMAND=doctor"
if not "%~1"=="" shift

if /I "%COMMAND%"=="doctor" goto run_doctor
if /I "%COMMAND%"=="install" goto run_install
if /I "%COMMAND%"=="stage-folder" goto run_stage
if /I "%COMMAND%"=="validate" goto run_validate
if /I "%COMMAND%"=="capstone" goto run_capstone
if /I "%COMMAND%"=="stage-decisions" goto run_decisions

echo Usage: resolve-kit {doctor^|install^|stage-folder^|validate^|capstone^|stage-decisions} [args...] 1>&2
exit /b 2

:run_doctor
python "%SCRIPT_DIR%\resolve_doctor.py" %*
exit /b %ERRORLEVEL%
:run_install
python "%SCRIPT_DIR%\install_resolve_kit.py" %*
exit /b %ERRORLEVEL%
:run_stage
python "%SCRIPT_DIR%\stage_folder_timeline.py" %*
exit /b %ERRORLEVEL%
:run_validate
python "%SCRIPT_DIR%\validate_timeline.py" %*
exit /b %ERRORLEVEL%
:run_capstone
python "%SCRIPT_DIR%\capstone_folder_pipeline.py" %*
exit /b %ERRORLEVEL%
:run_decisions
python "%SCRIPT_DIR%\stage_edit_decisions.py" %*
exit /b %ERRORLEVEL%
