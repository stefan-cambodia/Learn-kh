@echo off
rem FR-KH Learning - installation sous Windows : double-cliquez sur ce fichier.
rem Options transmises au script PowerShell : -Schedule ou -NoSchedule
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
if errorlevel 1 (
  echo.
  echo L'installation a rencontre un probleme : lisez les messages ci-dessus.
)
echo.
pause
