#Requires -Version 5.1
<#
    Traffic_Trace demo launcher.

    Cold laptop to a fully running system, with no internet, in under two
    minutes. Run it from this folder:

        .\start_demo.ps1

    It checks everything the demo depends on, prints the LAN address, the
    phone URLs and the three camera tokens, then starts the API and the
    dashboard in their own windows and waits until both actually answer.

    Every failure stops the script and prints the exact command that fixes it.
    A vague error at 9am is useless.

    For the deeper check (imports, model weights, pipeline placeholders), run
    api\scripts\preflight.py the night before. This script only verifies what
    it needs to start, so that demo morning stays fast.
#>

$ErrorActionPreference = 'Stop'

# Camera names contain em-dashes; without this the console renders them as
# mojibake and the token table becomes hard to read off.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$Root      = $PSScriptRoot
$Api       = Join-Path $Root 'api'
$Dash      = Join-Path $Root 'dashboard'
$Py        = Join-Path $Api  '.venv\Scripts\python.exe'
$Tiles     = Join-Path $Dash 'public\tiles'
$BuildId   = Join-Path $Dash '.next\BUILD_ID'
$PgService = 'postgresql-x64-18'
$HealthUrl = 'http://127.0.0.1:8000/api/health'
$DashUrl   = 'http://127.0.0.1:3000/camera'

$startedAt = Get-Date

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

function Step { param([string]$Message) Write-Host ""; Write-Host "==> $Message" -ForegroundColor Cyan }
function Ok   { param([string]$Message) Write-Host "    ok    $Message" -ForegroundColor Green }
function Note { param([string]$Message) Write-Host "          $Message" -ForegroundColor DarkGray }

function Die {
    param([string]$What, [string]$Fix)
    Write-Host ""
    Write-Host "  STOPPED: $What" -ForegroundColor Red
    Write-Host "  FIX:     $Fix"  -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Fix the above and run .\start_demo.ps1 again." -ForegroundColor Red
    Read-Host "  Press Enter to close"
    exit 1
}

# One attempt. Returns the response, or $null for any failure at all - a
# refused connection while a server is still booting is expected, not an error.
function Test-Url {
    param([string]$Url, [int]$TimeoutSec = 3)
    try { return Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec }
    catch { return $null }
}

# Poll until it answers. Polling, not Start-Sleep: uvicorn's first start loads
# torch and CLIP and can take 10-40s depending on the disk cache, and a blind
# sleep is either too short (false failure) or wastes demo-morning seconds.
function Wait-Url {
    param([string]$Url, [int]$Seconds)
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        $response = Test-Url -Url $Url -TimeoutSec 3
        if ($response -and $response.StatusCode -eq 200) { Write-Host ""; return $response }
        Write-Host "." -NoNewline -ForegroundColor DarkGray
        Start-Sleep -Milliseconds 700
    }
    Write-Host ""
    return $null
}

Write-Host ""
Write-Host "  Traffic_Trace - demo startup" -ForegroundColor White
Write-Host "  $Root" -ForegroundColor DarkGray

# ---------------------------------------------------------------------------
# 1. The files this script cannot work without
# ---------------------------------------------------------------------------

Step "Checking the project layout"

if (-not (Test-Path -LiteralPath $Py)) {
    Die "the API virtual environment is missing ($Py)" `
        "cd `"$Api`"; py -3.12 -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt -r ..\pipeline\requirements.txt"
}
if (-not (Test-Path -LiteralPath (Join-Path $Api '.env'))) {
    Die "api\.env is missing, so the API cannot find the database" `
        "Copy api\.env.example to api\.env and set DATABASE_URL, OFFICER_PIN"
}
if (-not (Test-Path -LiteralPath (Join-Path $Dash 'package.json'))) {
    Die "the dashboard folder is missing ($Dash)" `
        "dashboard\ is a separate git repo. Clone Traffic-Trace-Frontend into $Dash"
}
Ok "venv, api\.env and dashboard\ all present"

# ---------------------------------------------------------------------------
# 2. PostgreSQL
# ---------------------------------------------------------------------------

Step "PostgreSQL service"

$service = Get-Service -Name $PgService -ErrorAction SilentlyContinue
if (-not $service) {
    Die "the Windows service '$PgService' does not exist" `
        "PostgreSQL 18 is not installed on this machine. There is no Docker fallback here - install PostgreSQL 18 natively."
}
if ($service.Status -ne 'Running') {
    Note "service is $($service.Status), starting it"
    try {
        Start-Service -Name $PgService
        $service.WaitForStatus('Running', '00:00:40')
    } catch {
        Die "'$PgService' would not start: $($_.Exception.Message)" `
            "Run as Administrator, or open services.msc and start '$PgService' by hand. Check the Postgres log in its data\log folder."
    }
    Ok "started $PgService"
} else {
    Ok "$PgService already running"
}

# ---------------------------------------------------------------------------
# 3. Database, schema and camera tokens
#    The venv python is used rather than psql, so this reads the same
#    DATABASE_URL from api\.env that the API itself will use. A password typed
#    in two places is a password that drifts.
# ---------------------------------------------------------------------------

Step "Database, schema and camera tokens"

$probe = @'
import sys
sys.stdout.reconfigure(encoding="utf-8")
from app.core.config import settings
from app.db.session import get_connection

WANTED = ["cameras", "sightings", "incidents", "matches", "journeys"]
try:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
        present = {r["table_name"] for r in cur.fetchall()}
        missing = [t for t in WANTED if t not in present]
        if missing:
            print("ERROR|schema incomplete, missing tables: " + ", ".join(missing))
            sys.exit(1)
        cur.execute("SELECT name, token, lat, lng FROM cameras ORDER BY name")
        rows = cur.fetchall()
except Exception as exc:
    print(f"ERROR|{type(exc).__name__}: {exc}")
    sys.exit(1)

print(f"COUNT|{len(rows)}")
for r in rows:
    print(f"CAM|{r['name']}|{r['token']}|{r['lat']:.5f}|{r['lng']:.5f}")
# Read out of .env for the same reason as the tokens: a PIN printed from a
# second copy is a PIN that drifts, and it is discovered mid-demo.
print(f"PIN|{settings.OFFICER_PIN}")
'@

Push-Location -LiteralPath $Api
$probeOut = $probe | & $Py -
$probeCode = $LASTEXITCODE
Pop-Location

if ($probeCode -ne 0) {
    $reason = ($probeOut | Where-Object { $_ -like 'ERROR|*' }) -replace '^ERROR\|', ''
    if (-not $reason) { $reason = ($probeOut -join ' ') }
    # The probe died before it could print anything - an import error, usually.
    # Its traceback went to stderr, which is already on screen above. Say so
    # rather than printing "cannot query the database: " with nothing after it.
    if (-not $reason) { $reason = 'the probe printed nothing - its Python traceback is above this line' }
    if ($reason -like '*missing tables*') {
        Die "database reachable but $reason" `
            "psql -U postgres -d traffic_trace -f `"$Root\contracts\schema.sql`""
    }
    Die "cannot query the database: $reason" `
        "Check DATABASE_URL in api\.env, and that the traffic_trace database exists: psql -U postgres -l"
}

$cameraCount = [int](($probeOut | Where-Object { $_ -like 'COUNT|*' }) -split '\|')[1]
if ($cameraCount -ne 3) {
    Die "expected 3 seeded cameras, found $cameraCount" `
        "cd `"$Api`"; .\.venv\Scripts\python.exe -m scripts.seed_cameras"
}
Ok "all 5 tables present, 3 cameras seeded"

$cameras = @()
foreach ($line in ($probeOut | Where-Object { $_ -like 'CAM|*' })) {
    $parts = $line -split '\|'
    $cameras += [pscustomobject]@{ Name = $parts[1]; Token = $parts[2]; Lat = $parts[3]; Lng = $parts[4] }
}

$officerPin = (($probeOut | Where-Object { $_ -like 'PIN|*' }) -split '\|')[1]

# tools\tokens.json is what tools\replay.py authenticates with, and replay.py is
# the fallback if the phones fail on stage. Writing it here, from the tokens we
# just read out of the database, means the fallback is armed on every startup -
# rather than depending on someone having run scripts\seed_cameras.py since the
# last reseed. Keys are cam-A/B/C in camera order, matching the recording folder
# names replay.py expects.
$tokenMap = [ordered]@{}
for ($i = 0; $i -lt $cameras.Count; $i++) {
    $tokenMap["cam-$([char](65 + $i))"] = $cameras[$i].Token
}
$toolsDir = Join-Path $Root 'tools'
if (-not (Test-Path -LiteralPath $toolsDir)) { New-Item -ItemType Directory -Path $toolsDir | Out-Null }
$tokensPath = Join-Path $toolsDir 'tokens.json'
# WITHOUT a BOM. Windows PowerShell 5.1's `Out-File -Encoding utf8` prepends
# EF BB BF, and Python's json.load on a plain open() then dies with
# "Expecting value: line 1 column 1" - so replay.py, the stage fallback, would
# crash at the worst possible moment. .NET's UTF8Encoding($false) omits it.
[System.IO.File]::WriteAllText(
    $tokensPath,
    ($tokenMap | ConvertTo-Json),
    (New-Object System.Text.UTF8Encoding $false)
)
Ok "wrote tools\tokens.json - replay.py fallback is armed"

# ---------------------------------------------------------------------------
# 4. Offline map tiles - the venue has no internet, so a missing cache means a
#    grey map on stage and no way to fix it there.
# ---------------------------------------------------------------------------

Step "Offline map tiles"

$tileCount = 0
if (Test-Path -LiteralPath $Tiles) {
    $tileCount = (Get-ChildItem -LiteralPath $Tiles -Recurse -File -Filter '*.png' -ErrorAction SilentlyContinue).Count
}
if ($tileCount -eq 0) {
    Die "no cached map tiles in $Tiles - the map and journey pages would render as blank grey squares" `
        "cd `"$Api`"; .\.venv\Scripts\python.exe -m scripts.download_tiles   -- THIS NEEDS INTERNET, so it cannot be done at the venue."
}
if ($tileCount -lt 200) {
    Write-Host "    warn  only $tileCount tiles cached (~714 expected) - the map may go grey when panned" -ForegroundColor Yellow
} else {
    Ok "$tileCount tiles cached"
}

# ---------------------------------------------------------------------------
# 5. LAN address - the phones need it, and it changes with every hotspot
# ---------------------------------------------------------------------------

Step "Network"

# The trailing Select-Object matters: an adapter can hold more than one IPv4
# address, and an array here would print as "http://10.0.0.4 10.0.0.9:3000".
$lanIp = (Get-NetIPConfiguration |
          Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up' } |
          Select-Object -First 1).IPv4Address.IPAddress | Select-Object -First 1

if (-not $lanIp) {
    $lanIp = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
              Where-Object { $_.IPAddress -notmatch '^(127\.|169\.254\.)' } |
              Select-Object -First 1).IPAddress | Select-Object -First 1
}
if (-not $lanIp) {
    Die "this laptop has no usable IPv4 address, so no phone can reach it" `
        "Turn the phone hotspot on and connect the laptop to it, then run this script again. Confirm with: ipconfig"
}
Ok "laptop is $lanIp"

# ---------------------------------------------------------------------------
# 6. Start the API (own window, so it survives and its log stays readable)
# ---------------------------------------------------------------------------

Step "API on :8000"

if (Test-Url -Url $HealthUrl -TimeoutSec 2) {
    Ok "already running - left alone"
} else {
    $apiCmd = "`$Host.UI.RawUI.WindowTitle = 'Traffic_Trace API :8000'; " +
              "Set-Location -LiteralPath '$Api'; " +
              "& '$Py' -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
    Start-Process -FilePath 'powershell.exe' -ArgumentList "-NoExit -Command `"$apiCmd`"" | Out-Null
    Note "launched in its own window (loading YOLO + CLIP + ALPR takes a moment)"
}

# ---------------------------------------------------------------------------
# 7. Start the dashboard - PRODUCTION build, always.
#    `npm run dev` ships ~4 MB of JavaScript that never finishes loading over a
#    phone hotspot: the page renders but never hydrates, so every button
#    silently does nothing. This was a real, painful bug. Never use dev here.
# ---------------------------------------------------------------------------

Step "Dashboard on :3000"

$dashAlreadyUp = [bool](Test-Url -Url $DashUrl -TimeoutSec 2)

if ($dashAlreadyUp) {
    Ok "already running - left alone"
    # Something answers on :3000, but nothing on the wire says whether it is
    # `next start` or `next dev`, and a dev server here is the failure that
    # wastes the demo: the phone renders the page and then never hydrates.
    Note "if you started that one with 'npm run dev', close it and re-run this script -"
    Note "the phones will load the page but no button will ever respond."
} else {
    # Only build when there is no build. A rebuild on demo morning costs 30+
    # seconds for nothing.
    if (Test-Path -LiteralPath $BuildId) {
        Ok "existing production build found ($(Get-Content -LiteralPath $BuildId)) - not rebuilding"
    } else {
        Note "no production build - building now, this takes ~40s and only happens once"
        Push-Location -LiteralPath $Dash
        & npm.cmd run build
        $buildCode = $LASTEXITCODE
        Pop-Location
        if ($buildCode -ne 0 -or -not (Test-Path -LiteralPath $BuildId)) {
            Die "the dashboard production build failed (npm exit $buildCode)" `
                "Read the build output above. If node_modules is missing: cd `"$Dash`"; npm install"
        }
        Ok "built"
    }

    $dashCmd = "`$Host.UI.RawUI.WindowTitle = 'Traffic_Trace Dashboard :3000'; " +
               "Set-Location -LiteralPath '$Dash'; " +
               "npm.cmd run start -- -H 0.0.0.0 -p 3000"
    Start-Process -FilePath 'powershell.exe' -ArgumentList "-NoExit -Command `"$dashCmd`"" | Out-Null
    Note "launched in its own window"
}

# ---------------------------------------------------------------------------
# 8. Wait for both to actually answer
# ---------------------------------------------------------------------------

Step "Waiting for both servers to answer"

Write-Host "    api   " -NoNewline
$healthResponse = Wait-Url -Url $HealthUrl -Seconds 120
if (-not $healthResponse) {
    Die "the API never answered $HealthUrl within 120s" `
        "Look at the 'Traffic_Trace API :8000' window - the traceback is in it. Common causes: port 8000 already taken by an old run, or a pipeline import error. Then run: cd `"$Api`"; .\.venv\Scripts\python.exe -m scripts.preflight"
}

$health = $healthResponse.Content | ConvertFrom-Json

if (-not $health.db.ok) {
    Die "the API is up but cannot reach Postgres: $($health.db.error)" `
        "Check DATABASE_URL in api\.env and that '$PgService' is still running"
}
Ok "API healthy - $($health.db.database) on $($health.db.version)"

# The single most dangerous failure mode: a stub pipeline produces green
# counters, plausible incidents and completely invented data. Refuse to call
# that ready.
if (-not $health.pipeline.real) {
    Die "the API started with a STUB pipeline - every sighting would be fabricated ($($health.pipeline.status))" `
        "Close the API window, then: cd `"$Api`"; .\.venv\Scripts\python.exe -m scripts.preflight   (it names the missing import). Note that a missing fast_alpr breaks the whole pipeline, not just plate reading."
}
Ok "real AI pipeline loaded - $($health.pipeline.status)"

Write-Host "    dash  " -NoNewline
if (-not (Wait-Url -Url $DashUrl -Seconds 90)) {
    Die "the dashboard never answered $DashUrl within 90s" `
        "Look at the 'Traffic_Trace Dashboard :3000' window. If port 3000 is taken by an old run, close it and re-run this script."
}
Ok "dashboard serving the production build"

# ---------------------------------------------------------------------------
# 9. READY
# ---------------------------------------------------------------------------

$elapsed = [int]((Get-Date) - $startedAt).TotalSeconds

Write-Host ""
Write-Host "  ============================================================" -ForegroundColor Green
Write-Host "   READY  -  everything up in $elapsed seconds" -ForegroundColor Green
Write-Host "  ============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "   LAPTOP IP     $lanIp" -ForegroundColor White
Write-Host ""
Write-Host "   ON THE PHONES" -ForegroundColor White
Write-Host "     camera page   http://${lanIp}:3000/camera"
Write-Host ""
Write-Host "   ON THE LAPTOP / PROJECTOR" -ForegroundColor White
Write-Host "     incidents     http://localhost:3000/incidents"
Write-Host "     live map      http://localhost:3000/map"
Write-Host "     journeys      http://localhost:3000/journeys"
Write-Host "     api health    http://localhost:8000/api/health"
Write-Host "     api docs      http://localhost:8000/docs"
Write-Host ""
Write-Host "   CAMERA TOKENS  (paste into each phone's /camera page)" -ForegroundColor White
foreach ($camera in $cameras) {
    Write-Host ("     {0,-32} {1}" -f $camera.Name, $camera.Token) -ForegroundColor Yellow
    Write-Host ("     {0,-32} {1}, {2}" -f '', $camera.Lat, $camera.Lng) -ForegroundColor DarkGray
}
Write-Host ""
Write-Host "   BEFORE THE PHONES WILL WORK" -ForegroundColor White
Write-Host "     Each phone's Chrome flag must contain this EXACT origin:" -ForegroundColor DarkGray
Write-Host "       chrome://flags  ->  unsafely-treat-insecure-origin-as-secure  ->  http://${lanIp}:3000" -ForegroundColor Yellow
Write-Host "     It gates BOTH the camera and the GPS. Relaunch Chrome after setting it." -ForegroundColor DarkGray
Write-Host "     The camera page shows a green 'JS ready' badge when the page is really alive." -ForegroundColor DarkGray
Write-Host ""
Write-Host "     If a phone cannot reach the laptop AT ALL, it is Windows Firewall, not the app." -ForegroundColor DarkGray
Write-Host "     In an Administrator PowerShell, once per machine:" -ForegroundColor DarkGray
Write-Host '       netsh advfirewall firewall add rule name="Traffic_Trace" dir=in action=allow protocol=TCP localport=3000,8000' -ForegroundColor Yellow
Write-Host ""
Write-Host "   Officer PIN $officerPin unlocks confirm/reject and the demo reset." -ForegroundColor DarkGray
Write-Host "   The two server windows must stay open. Closing one kills that server." -ForegroundColor DarkGray
Write-Host ""

Read-Host "  Press Enter to close this window (the servers keep running)"
