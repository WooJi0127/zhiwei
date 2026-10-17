@echo off
chcp 65001 >nul 2>&1
setlocal

rem ============================================================
rem  知未 · 注册每日自动更新（只需双击一次）
rem
rem  每天 08:00 跑 tools\daily_update.py：
rem      抓最新回归名单 → 入库 → 导出 data/data.js → 分发到各端
rem  不重新打安装包（要新安装包请手动跑 build.bat）
rem
rem  改时间：把下面的 08:00 改掉，再双击一次即可覆盖。
rem  取消：schtasks /Delete /TN "ZhiweiDaily" /F
rem ============================================================

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "PY=C:\Users\13956\.workbuddy\binaries\python\versions\3.13.12\python.exe"
if not exist "%PY%" (
    where py >nul 2>&1 && (set "PY=py") || (set "PY=python")
)

set "TASKNAME=ZhiweiDaily"
set "TR=\"%PY%\" \"%ROOT%\tools\daily_update.py\""

echo.
echo === 知未 · 注册每日自动更新 ===
echo 任务名   : %TASKNAME%
echo 运行时间 : 每天 08:00
echo 命令     : %TR%
echo.

schtasks /Create /TN "%TASKNAME%" /TR "%TR%" /SC DAILY /ST 08:00 /F

if "%ERRORLEVEL%"=="0" (
    echo.
    echo [OK] 已注册，每天 08:00 自动更新数据。
    echo      查看：schtasks /Query /TN "%TASKNAME%"
    echo      取消：schtasks /Delete /TN "%TASKNAME%" /F
) else (
    echo.
    echo [FAIL] 注册失败。如果没有管理员权限，
    echo        就用管理员身份重开这个文件，或者手动双击 update.bat。
)

echo.
endlocal
pause
