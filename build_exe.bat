@echo off
echo ===================================================
echo Memulai Kompilasi DeepSeek4Free ke Windows EXE...
echo ===================================================
.venv\Scripts\python.exe build_exe.py --onefile
echo ===================================================
echo Selesai! File EXE tersedia di: dist\deepseek-server.exe
echo ===================================================
pause
