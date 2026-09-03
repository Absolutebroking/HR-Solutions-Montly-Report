@echo off
echo Refreshing the attendance dashboard from every month folder...
echo.
python refresh_all.py
echo.
echo ----------------------------------------------------------------
echo Done. If you saw any WARNING lines above, fix those rows in the
echo relevant month's CSV and run this file again. Otherwise, refresh
echo index.html in your browser (Ctrl+Shift+R) to see the update.
echo ----------------------------------------------------------------
pause
