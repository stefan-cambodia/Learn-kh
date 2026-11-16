# FR-KH Learning — installation sous Windows (PowerShell 5.1 ou plus récent).
#
#   Double-cliquez sur scripts\install.bat, ou bien, dans PowerShell :
#     powershell -ExecutionPolicy Bypass -File scripts\install.ps1
#     powershell -ExecutionPolicy Bypass -File scripts\install.ps1 -Schedule     (active la tâche planifiée)
#     powershell -ExecutionPolicy Bypass -File scripts\install.ps1 -NoSchedule   (ne touche pas à la planification)
#
# Le script peut être relancé sans risque : il ne remplace ni .env, ni la configuration,
# ni la base de données, ni les leçons déjà générées.

param([switch]$Schedule, [switch]$NoSchedule)

$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$env:PYTHONUTF8 = "1"
Set-Location (Join-Path $PSScriptRoot "..")
$Root = (Get-Location).Path

function Say($text) { Write-Host ""; Write-Host "== $text" -ForegroundColor Cyan }

Say "1/5  Python"
$Python = $null
foreach ($candidate in @(@("py", "-3"), @("python"), @("python3"))) {
    $exe = $candidate[0]
    $pre = @($candidate | Select-Object -Skip 1)
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
    try {
        $found = & $exe @pre -c "import sys; print(sys.executable if sys.version_info >= (3, 9) else '')" 2>$null
        if ($LASTEXITCODE -eq 0 -and $found -and (Test-Path $found.Trim())) { $Python = $found.Trim(); break }
    } catch { }
}
if (-not $Python) {
    Write-Host "Python 3.9 ou plus récent est nécessaire." -ForegroundColor Red
    Write-Host "Installez-le depuis https://www.python.org/downloads/ (cochez « Add python.exe to PATH »),"
    Write-Host "ou avec : winget install Python.Python.3.12   puis relancez ce script."
    exit 1
}
Write-Host "Python trouvé : $Python"

# Sous Windows, la base des fuseaux horaires vient du paquet « tzdata » (facultatif :
# sans lui, le décalage fixe du Cambodge, UTC+7, est utilisé).
& $Python -c "import zoneinfo; zoneinfo.ZoneInfo('Asia/Phnom_Penh')" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installation du paquet tzdata (fuseaux horaires)..."
    try { & $Python -m pip install --quiet --user tzdata 2>$null } catch { }
    & $Python -c "import zoneinfo; zoneinfo.ZoneInfo('Asia/Phnom_Penh')" 2>$null
    if ($LASTEXITCODE -ne 0) { Write-Host "tzdata non installé : le décalage fixe UTC+7 du Cambodge sera utilisé." }
}

Say "2/5  Fichier des clés API (.env)"
if (Test-Path ".env") {
    Write-Host ".env existe déjà : il est conservé tel quel."
} else {
    Copy-Item ".env.example" ".env"
    Write-Host ".env créé à partir de .env.example : ajoutez-y vos clés API."
}

Say "3/5  Dossiers, base de données et configuration"
& $Python manage.py init
if ($LASTEXITCODE -ne 0) { exit 1 }

Say "4/5  Vérification générale"
& $Python manage.py check

Say "5/5  Génération automatique quotidienne"
$install = $false
if ($Schedule) { $install = $true }
elseif (-not $NoSchedule) {
    $answer = Read-Host "Activer la génération automatique (07h00, heure du Cambodge) ? [O/n]"
    if ($answer -eq "" -or $answer -match "^[oOyY]") { $install = $true }
}
if ($install) {
    & $Python manage.py schedule install
} else {
    Write-Host "Planification non installée. Pour l'activer plus tard : python manage.py schedule install"
}

Write-Host ""
Write-Host "Installation terminée dans $Root" -ForegroundColor Green
Write-Host ""
Write-Host "Étapes suivantes :"
Write-Host "  1. Clés API   : éditez .env (guides : docs\GOOGLE_CLOUD_TTS.md et docs\AZURE_SPEECH_KHMER.md)"
Write-Host "  2. Prénoms    : éditez config\config.json, rubrique « learners » (avant la première leçon)"
Write-Host "  3. Essai voix : python manage.py tts test"
Write-Host "  4. 1re leçon  : scripts\run.bat"
Write-Host "  5. Lecture    : ouvrez index.html dans votre navigateur"
exit 0
