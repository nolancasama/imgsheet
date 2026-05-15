@echo off
cd /d C:\Users\nolan\imgsheet
python -m uvicorn web.server:app --reload --port 8000
