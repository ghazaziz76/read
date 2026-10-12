@echo off
rem Rebuild the bridge pages from the live newsletter data and publish them.
cd /d "%~dp0"
python build.py || exit /b 1
git add -A
git commit -m "Update bridge pages" || echo Nothing new to publish.
git push
