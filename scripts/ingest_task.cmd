@echo off
rem Automatischer Ingest fuer die Windows-Aufgabenplanung.
rem Haengt die Zusammenfassung an logs\ingest.log an (nur Zaehler und
rem Dokumentnamen, kein PII — siehe CLAUDE.md).
cd /d "%~dp0.."
if not exist logs mkdir logs
echo. >> logs\ingest.log
echo ===== Ingest %date% %time% ===== >> logs\ingest.log
venv\Scripts\python.exe scripts\ingest.py >> logs\ingest.log 2>&1
