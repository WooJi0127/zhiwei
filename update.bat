@echo off
chcp 65001 >nul 2>&1
setlocal

rem ============================================================
rem  知未 · 只更新数据
rem  抓最新回归名单 → 入库 → 导出 data/data.js → 同步到所有端
rem  想连同安装包一起重新打包，请用 build.bat
rem ============================================================

cd /d "%~dp0"

set "PY=C:\Users\13956\.workbuddy\binaries\python\versions\3.13.12\python.exe"
if not exist "%PY%" (
    where py >nul 2>&1 && (set "PY=py") || (set "PY=python")
)

echo.
echo === ^知未 data update ===
echo Python: %PY%
echo.

"%PY%" "%~dp0tools\build_all.py" --web
set RC=%ERRORLEVEL%

echo.
if "%RC%"=="0" (
    echo [OK] Updated. Reload to see new data.
    echo      Offline single file: ^知未.html
    echo      Online version     : site\app\index.html
) else (
    echo [FAIL] Exit code %RC%. See .build-logs\ for full output.
)
echo.
pause
endlocal
