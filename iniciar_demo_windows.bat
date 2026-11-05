@echo off
cd /d %~dp0
call .venv\Scripts\activate
set TRADING_DEMO=1
streamlit run app.py
