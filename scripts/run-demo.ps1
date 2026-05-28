# scripts/run-demo.ps1
# Launches the frontend-demo Vite dev server and force-opens Chrome
# once the server is ready. Vite runs in foreground; a background job
# polls localhost:5173 and opens Chrome.

$ErrorActionPreference = 'Stop'

# 1. Locate chrome.exe
$chromePaths = @(
    $env:CHROME_PATH,
    "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "${env:LocalAppData}\Google\Chrome\Application\chrome.exe"
)
$chrome = $chromePaths | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $chrome) {
    $chrome = (Get-Command chrome.exe -ErrorAction SilentlyContinue).Source
}
if (-not $chrome) {
    Write-Error 'Chrome not found. Set $env:CHROME_PATH or install Chrome.'
    exit 1
}

# 2. Resolve frontend dir relative to this script
$projectRoot = Split-Path $PSScriptRoot -Parent
$frontendDir = Join-Path $projectRoot 'frontend-demo'
$url = 'http://localhost:5173'

if (-not (Test-Path $frontendDir)) {
    Write-Error "frontend-demo directory not found at $frontendDir"
    exit 1
}

# 3. Install deps if needed
if (-not (Test-Path (Join-Path $frontendDir 'node_modules'))) {
    Write-Host 'Installing dependencies...' -ForegroundColor Cyan
    Push-Location $frontendDir
    try { npm install } finally { Pop-Location }
}

# 4. Background job: wait for Vite, then open Chrome
$openJob = Start-Job -ScriptBlock {
    param($url, $chrome)
    for ($i = 0; $i -lt 60; $i++) {
        try {
            $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 1
            if ($r.StatusCode -eq 200) {
                Start-Process -FilePath $chrome -ArgumentList $url
                return
            }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    Write-Host 'Vite did not start in 30s — opening Chrome anyway'
    Start-Process -FilePath $chrome -ArgumentList $url
} -ArgumentList $url, $chrome

# 5. Run Vite in foreground
Write-Host "Starting Vite at $url" -ForegroundColor Cyan
Push-Location $frontendDir
try {
    npm run dev
} finally {
    Remove-Job -Job $openJob -Force -ErrorAction SilentlyContinue
    Pop-Location
}
