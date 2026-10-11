param([switch]$PrepareOnly)
$ErrorActionPreference = 'Stop'
$repoRoot = $PSScriptRoot
$environmentPath = Join-Path $repoRoot '.env'
if (-not (Test-Path -LiteralPath $environmentPath)) {
    $buffer = New-Object byte[] 32
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($buffer) } finally { $generator.Dispose() }
    $databasePassword = [BitConverter]::ToString($buffer).Replace('-', '').ToLowerInvariant()
    $example = [IO.File]::ReadAllText((Join-Path $repoRoot '.env.example'))
    $configured = [regex]::Replace($example, '(?m)^POSTGRES_PASSWORD=.*$', ('POSTGRES_PASSWORD=' + $databasePassword))
    [IO.File]::WriteAllText($environmentPath, $configured, (New-Object Text.UTF8Encoding $false))
    Write-Host 'Created your ignored .env with a generated database password.'
} else {
    Write-Host 'Using your existing .env without changing its settings.'
}
if ($PrepareOnly) { return }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Install and start Docker Desktop, then run this script again.'
}
Push-Location $repoRoot
try {
    docker compose version
    if ($LASTEXITCODE -ne 0) { throw 'Docker Compose is unavailable.' }
    docker info --format '{{.ServerVersion}}'
    if ($LASTEXITCODE -ne 0) { throw 'Start Docker Desktop with Linux containers and try again.' }
    docker compose config --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Check .env settings and the Docker configuration.' }
    docker compose up -d --build
    if ($LASTEXITCODE -ne 0) { throw 'Startup failed. Read the Docker output above.' }
    Write-Host 'Open http://localhost:4000 after startup.'
    Write-Host 'Models download and warm up in the background on first launch.'
    Write-Host 'Check NLP readiness at http://localhost:8001/health and logs with: docker compose logs -f nlp-service'
} finally { Pop-Location }
