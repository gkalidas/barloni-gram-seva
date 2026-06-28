@echo off
REM One-click launcher for barloni-gram-seva (Windows).
REM Double-click this file to set up and start the app.
cd /d "%~dp0"

REM Prefer the Python launcher (py), then python on PATH.
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 start.py %*
    goto done
)

where python >nul 2>nul
if %errorlevel%==0 (
    python start.py %*
    goto done
)

echo.
echo Python 3.10 or newer was not found on this computer.
echo Please install it from https://www.python.org/downloads/
echo During installation, tick "Add Python to PATH", then run this file again.
echo.
pause
exit /b 1

:done
if %errorlevel% neq 0 (
    echo.
    echo Something went wrong. See the messages above.
    pause
)
