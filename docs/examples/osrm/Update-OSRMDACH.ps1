# Ford Triplog - OSRM DACH Update
# Version: 1.0
#
# Builds Germany + Austria + Switzerland OSRM data on Windows,
# tests it locally, uploads it to Synology, restarts OSRM and tests again.
#
# Requirements:
# - Docker Desktop (Linux containers)
# - PuTTY / pscp.exe / plink.exe
# - SSH key authentication to Synology
# - Recommended for DACH preprocessing: 32 GB RAM + SSD/NVMe

$ErrorActionPreference = "Stop"

$WorkDir = "C:\osrm"
$Image = "osrm/osrm-backend:latest"
$OsmiumImage = "iboates/osmium:latest"

$GermanyUrl = "https://download.geofabrik.de/europe/germany-latest.osm.pbf"
$AustriaUrl = "https://download.geofabrik.de/europe/austria-latest.osm.pbf"
$SwitzerlandUrl = "https://download.geofabrik.de/europe/switzerland-latest.osm.pbf"

$Pscp = "C:\Program Files\PuTTY\pscp.exe"
$Plink = "C:\Program Files\PuTTY\plink.exe"

# --- User configuration ---
$SshKey = "C:\Users\YOUR_USER\.ssh\synology.ppk"
$NasUser = "YOUR_NAS_USER"
$NasHost = "192.168.1.100"

$WorkDir = "C:\osrm"
$NasTarget = "/volume1/docker/osrm"
$NasContainer = "OSRM-Triplog"
$NasPort = 5005

$NasTarget = "/volume1/docker/osrm"
$NasContainer = "OSRM-Triplog"
$NasPort = 5005

$LocalTestPort = 5006
$LocalTestContainer = "OSRM-DACH-Test"

$TestCH = "8.9514,47.1757"
$TestDE = "9.6849,47.5460"
$TestAT = "9.7471,47.5031"

$StartTime = Get-Date

New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null
$LogFile = Join-Path $WorkDir ("osrm-dach-update-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")

function Step([string]$Text) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Text"
    Write-Host ""
    Write-Host $line -ForegroundColor Cyan
    Add-Content -Path $LogFile -Value $line
}

function Fail([string]$Text) {
    Write-Host ""
    Write-Host "ERROR: $Text" -ForegroundColor Red
    Add-Content -Path $LogFile -Value "ERROR: $Text"
    throw $Text
}

function Run([string]$Command, [string[]]$Arguments) {
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        Fail "$Command failed with exit code $LASTEXITCODE"
    }
}

function TestOsrm([string]$BaseUrl, [string]$Coordinate, [string]$Label) {
    $result = Invoke-RestMethod "$BaseUrl/nearest/v1/driving/$Coordinate" -TimeoutSec 30
    if ($result.code -ne "Ok") {
        Fail "$Label test failed"
    }
    Write-Host "$Label test: OK"
}

Step "Pre-flight checks"

if (-not (Test-Path $Pscp)) { Fail "pscp.exe not found: $Pscp" }
if (-not (Test-Path $Plink)) { Fail "plink.exe not found: $Plink" }
if (-not (Test-Path $SshKey)) { Fail "SSH key not found: $SshKey" }

Run "docker" @("version")
Run "docker" @("pull", $Image)
Run "docker" @("pull", $OsmiumImage)

$GermanyFile = Join-Path $WorkDir "germany-latest.osm.pbf"
$AustriaFile = Join-Path $WorkDir "austria-latest.osm.pbf"
$SwitzerlandFile = Join-Path $WorkDir "switzerland-latest.osm.pbf"
$DachPbf = Join-Path $WorkDir "dach-latest.osm.pbf"

Step "Download Germany"
Invoke-WebRequest $GermanyUrl -OutFile "$GermanyFile.download"
Move-Item -Force "$GermanyFile.download" $GermanyFile

Step "Download Austria"
Invoke-WebRequest $AustriaUrl -OutFile "$AustriaFile.download"
Move-Item -Force "$AustriaFile.download" $AustriaFile

Step "Download Switzerland"
Invoke-WebRequest $SwitzerlandUrl -OutFile "$SwitzerlandFile.download"
Move-Item -Force "$SwitzerlandFile.download" $SwitzerlandFile

Step "Remove old local DACH build"
Get-ChildItem $WorkDir -Filter "dach-latest.osrm*" -ErrorAction SilentlyContinue | Remove-Item -Force
if (Test-Path $DachPbf) { Remove-Item -Force $DachPbf }

Step "Merge DE + AT + CH"
Run "docker" @(
    "run","--rm",
    "-v","${WorkDir}:/data",
    $OsmiumImage,
    "merge",
    "/data/germany-latest.osm.pbf",
    "/data/austria-latest.osm.pbf",
    "/data/switzerland-latest.osm.pbf",
    "-o","/data/dach-latest.osm.pbf",
    "--overwrite"
)

if (-not (Test-Path $DachPbf)) { Fail "DACH PBF was not created" }

Step "osrm-extract"
Run "docker" @(
    "run","--rm",
    "-v","${WorkDir}:/data",
    $Image,
    "osrm-extract","-p","/opt/car.lua","/data/dach-latest.osm.pbf"
)

Step "osrm-partition"
Run "docker" @(
    "run","--rm",
    "-v","${WorkDir}:/data",
    $Image,
    "osrm-partition","/data/dach-latest.osrm"
)

Step "osrm-customize"
Run "docker" @(
    "run","--rm",
    "-v","${WorkDir}:/data",
    $Image,
    "osrm-customize","/data/dach-latest.osrm"
)

$OsrmFiles = @(Get-ChildItem $WorkDir -Filter "dach-latest.osrm*" -File)
if ($OsrmFiles.Count -lt 20) { Fail "Unexpected OSRM file count: $($OsrmFiles.Count)" }

$TotalBytes = ($OsrmFiles | Measure-Object Length -Sum).Sum
$TotalGiB = [Math]::Round($TotalBytes / 1GB, 2)

Step "Local OSRM test"

& docker rm -f $LocalTestContainer 2>$null | Out-Null

Run "docker" @(
    "run","-d",
    "--name",$LocalTestContainer,
    "-p","${LocalTestPort}:5000",
    "-v","${WorkDir}:/data",
    $Image,
    "osrm-routed","--algorithm","mld","/data/dach-latest.osrm"
)

try {
    $Ready = $false
    for ($i=0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 2
        try {
            $r = Invoke-RestMethod "http://127.0.0.1:$LocalTestPort/nearest/v1/driving/$TestCH" -TimeoutSec 5
            if ($r.code -eq "Ok") { $Ready = $true; break }
        } catch {}
    }

    if (-not $Ready) { Fail "Local OSRM server did not become ready" }

    TestOsrm "http://127.0.0.1:$LocalTestPort" $TestCH "CH"
    TestOsrm "http://127.0.0.1:$LocalTestPort" $TestDE "DE"
    TestOsrm "http://127.0.0.1:$LocalTestPort" $TestAT "AT"

    $cross = Invoke-RestMethod "http://127.0.0.1:$LocalTestPort/route/v1/driving/$TestCH;$TestAT?overview=false" -TimeoutSec 30
    if ($cross.code -ne "Ok") { Fail "Cross-border CH -> AT test failed" }
    Write-Host "Cross-border CH -> AT: OK"
}
finally {
    & docker rm -f $LocalTestContainer 2>$null | Out-Null
}

Step "Upload OSRM files to Synology"

$PscpArgs = @("-batch","-i",$SshKey)
$PscpArgs += $OsrmFiles.FullName
$PscpArgs += "${NasUser}@${NasHost}:${NasTarget}/"
Run $Pscp $PscpArgs

Step "Verify uploaded file count"

$RemoteCountOutput = & $Plink -batch -i $SshKey "${NasUser}@${NasHost}" "find '$NasTarget' -maxdepth 1 -type f -name 'dach-latest.osrm*' | wc -l"
if ($LASTEXITCODE -ne 0) { Fail "Remote verification failed" }

$RemoteCount = [int](($RemoteCountOutput | Select-Object -Last 1).Trim())
if ($RemoteCount -ne $OsrmFiles.Count) {
    Fail "File count mismatch: local=$($OsrmFiles.Count), remote=$RemoteCount"
}

Step "Restart production OSRM container"

$RemoteRestart = "docker stop $NasContainer >/dev/null 2>&1 || true; docker rm $NasContainer >/dev/null 2>&1 || true; docker run -d --name $NasContainer --restart unless-stopped -p ${NasPort}:5000 -v ${NasTarget}:/data $Image osrm-routed --algorithm mld /data/dach-latest.osrm"

& $Plink -batch -i $SshKey "${NasUser}@${NasHost}" $RemoteRestart
if ($LASTEXITCODE -ne 0) { Fail "Remote OSRM restart failed" }

Step "Final NAS test"

$NasReady = $false
for ($i=0; $i -lt 60; $i++) {
    Start-Sleep -Seconds 2
    try {
        $r = Invoke-RestMethod "http://${NasHost}:${NasPort}/nearest/v1/driving/$TestCH" -TimeoutSec 5
        if ($r.code -eq "Ok") { $NasReady = $true; break }
    } catch {}
}
if (-not $NasReady) { Fail "Synology OSRM did not become ready" }

TestOsrm "http://${NasHost}:${NasPort}" $TestCH "Synology CH"
TestOsrm "http://${NasHost}:${NasPort}" $TestDE "Synology DE"
TestOsrm "http://${NasHost}:${NasPort}" $TestAT "Synology AT"

$Elapsed = (Get-Date) - $StartTime

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host " OSRM DACH UPDATE COMPLETED" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host "Files:    $($OsrmFiles.Count)"
Write-Host "Size:     $TotalGiB GiB"
Write-Host "Duration: $Elapsed"
Write-Host "NAS:      http://${NasHost}:${NasPort}"
Write-Host "Log:      $LogFile"
