@echo off
setlocal
cd /d %~dp0
if not exist .venv-win (
    py -m venv .venv-win
)
call .venv-win\Scripts\activate
python -m pip install -r requirements.txt
python -m app.main
endlocal
