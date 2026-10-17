@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

rem ============================================================
rem  知未 · 一键构建
rem
rem  双击         全量：抓数据 → 自检 → 同步 → 打 Windows APK → 更新下载站
rem  build.bat --no-data   不抓数据，只重新打包（改界面时用）
rem  build.bat --web       只生成网页版（最快，改样式时用）
rem  build.bat --test      打包前先跑冒烟测试和布局检查
rem ============================================================

cd /d "%~dp0"

set "PY=C:\Users\13956\.workbuddy\binaries\python\versions\3.13.12\python.exe"
if not exist "%PY%" (
    where py >nul 2>&1 && (set "PY=py") || (set "PY=python")
)

echo.
echo === ^知未 build ===
echo Python: %PY%
echo Args  : %*
echo.

rem 这台机器上残留的 ELECTRON_RUN_AS_NODE 会让打包出的 exe 起不来，先清掉
set "ELECTRON_RUN_AS_NODE="

"%PY%" "%~dp0tools\build_all.py" %*
set RC=%ERRORLEVEL%

echo.
if "%RC%"=="0" (
    echo [OK] Build finished.
) else (
    echo [FAIL] Exit code %RC%. See .build-logs\ for full output.
)
echo.
pause
endlocal
