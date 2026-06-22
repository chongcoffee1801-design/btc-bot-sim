@echo off
echo ========================================
echo  BTC Paper Trade Dashboard
echo ========================================
echo.
echo เปิด browser ที่ http://localhost:8501
echo กด Ctrl+C เพื่อหยุด
echo.
streamlit run dashboard.py --server.port 8501
pause
