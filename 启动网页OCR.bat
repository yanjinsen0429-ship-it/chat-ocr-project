@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "URL=http://127.0.0.1:5000"
set "PORT=5000"

where python >nul 2>nul
if errorlevel 1 (
    powershell -NoProfile -Command "Write-Host ([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('5pyq5qOA5rWL5YiwIFB5dGhvbiDnjq/looPvvIzor7flhYjlronoo4UgUHl0aG9u44CC')))"
    pause
    exit /b 1
)

call :find_port_pid
if defined PORT_PID (
    powershell -NoProfile -Command "Write-Host ([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('5qOA5rWL5Yiw5bey5pyJIE9DUiDmnI3liqHmraPlnKjov5DooYzjgII=')))"
    powershell -NoProfile -Command "Write-Host ([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('5piv5ZCm5YWz6Zet5pen5pyN5Yqh5bm26YeN5paw5ZCv5Yqo77yfKFkvTik=')))"
    choice /C YN /N /M "> "
    if errorlevel 2 (
        powershell -NoProfile -Command "Write-Host ([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('5LiN5YWz6Zet5pen5pyN5Yqh77yM5bey5omT5byA5bey5pyJ572R6aG144CC')))"
        start "" "%URL%"
        pause
        exit /b 0
    )
    if errorlevel 1 (
        echo Closing old OCR service PID %PORT_PID% ...
        taskkill /PID %PORT_PID% /F
        timeout /t 1 /nobreak >nul
        goto start_service
    )
)

:start_service
echo Starting OCR web service...
echo Browser will open %URL%
echo.
python web_app.py

echo.
echo OCR web service exited.
pause
exit /b 0

:find_port_pid
set "PORT_PID="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%PORT% .*LISTENING"') do (
    set "PORT_PID=%%P"
    goto :eof
)
goto :eof
