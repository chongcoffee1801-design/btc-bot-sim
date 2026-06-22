@echo off
echo ========================================
echo  BTC 4-Layer Paper Trade Bot - Setup
echo ========================================

echo.
echo [1/3] Installing Python packages...
pip install -r requirements.txt

echo.
echo [2/3] Creating data folder...
if not exist "data" mkdir data
if not exist "logs" mkdir logs

echo.
echo [3/3] Done! Starting bot...
echo.
echo Bot จะรันทุกวัน 07:05 น. (ไทย)
echo กด Ctrl+C เพื่อหยุด
echo.
python bot_sim.py

pause
