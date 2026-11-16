@echo off
rem FR-KH Learning - lancement manuel sous Windows.
rem
rem   scripts\run.bat                      genere la lecon du jour (sans attendre 07h00)
rem   scripts\run.bat --date 2026-01-31    genere la lecon d'une date precise
rem   scripts\run.bat --open               genere, puis ouvre le site dans le navigateur
rem
rem Sans danger si la lecon existe deja : rien n'est cree en double.
setlocal
cd /d "%~dp0.."
set PYTHONUTF8=1
chcp 65001 >nul

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (where python >nul 2>nul && set "PY=python")
if not defined PY (
  echo Python 3 est introuvable : lancez d'abord scripts\install.bat
  pause
  exit /b 1
)

set "OPEN="
set "INTERACTIVE="
if "%~1"=="" set "INTERACTIVE=1"
if /i "%~1"=="--open" (
  set "OPEN=1"
  shift
)

%PY% manage.py generate %1 %2 %3 %4
set "CODE=%errorlevel%"
echo.
echo Site : %cd%\index.html
if defined OPEN start "" "%cd%\index.html"
if defined INTERACTIVE pause
exit /b %CODE%
