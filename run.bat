@echo off
python imgsheet.py
if errorlevel 1 (
    echo.
    echo Something went wrong. See the error above.
    pause
)
