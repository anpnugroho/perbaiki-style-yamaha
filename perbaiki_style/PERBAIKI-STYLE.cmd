@echo off
REM ===== Perbaiki Style (Yamaha PSR) - launcher =====
REM Server dijalankan di WSL (Python 3). Tidak perlu install apa pun di Windows.
title Perbaiki Style - server (biarkan jendela ini terbuka)
echo.
echo   Menyalakan server "Perbaiki Style"...
echo   Tutup jendela ini kalau sudah selesai (server ikut berhenti).
echo.

start "" /min wsl.exe -e bash -lc "cd /mnt/d/Projects/openclaw/yamaha-style/perbaiki_style && python3 app.py --host 0.0.0.0 --port 3210"

timeout /t 3 /nobreak >nul

set WSLIP=
for /f "usebackq tokens=*" %%i in (`wsl.exe -e bash -lc "hostname -I"`) do set WSLIP=%%i

echo   Buka di browser:  http://localhost:3210
if not "%WSLIP%"=="" echo   Kalau tidak bisa, coba:  http://%WSLIP%:3210
echo.

start "" http://localhost:3210

timeout /t 8 /nobreak >nul
exit /b 0
