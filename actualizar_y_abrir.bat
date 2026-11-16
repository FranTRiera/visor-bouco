@echo off
REM Descarga los anuncios nuevos del BOUCO y abre el visor.
cd /d "%~dp0"
python scraper.py
start "" "%~dp0index.html"

