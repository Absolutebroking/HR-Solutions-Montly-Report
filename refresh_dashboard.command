#!/bin/bash
cd "$(dirname "$0")"
echo "Refreshing the attendance dashboard from every month folder..."
echo
python3 refresh_all.py
echo
echo "----------------------------------------------------------------"
echo "Done. If you saw any WARNING lines above, fix those rows in the"
echo "relevant month's CSV and run this file again. Otherwise, refresh"
echo "index.html in your browser (Cmd+Shift+R) to see the update."
echo "----------------------------------------------------------------"
read -p "Press Enter to close..."
