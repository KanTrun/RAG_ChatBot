$ErrorActionPreference = "Stop"

function Test-PortOccupied {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    return @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue).Count -gt 0
}

function Test-PortBindable {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    $listener = $null
    try {
        $listener = [System.Net.Sockets.TcpListener]::new(
            [System.Net.IPAddress]::Parse("127.0.0.1"),
            $Port
        )
        $listener.Start()
        return $true
    } catch {
        return $false
    } finally {
        if ($listener -ne $null) {
            $listener.Stop()
        }
    }
}

function Get-FreePort {
    param(
        [Parameter(Mandatory = $true)]
        [int]$PreferredPort
    )

    foreach ($candidate in $PreferredPort..($PreferredPort + 20)) {
        if (Test-PortOccupied -Port $candidate) {
            continue
        }
        if (Test-PortBindable -Port $candidate) {
            return $candidate
        }
    }

    $fallbackListener = $null
    try {
        $fallbackListener = [System.Net.Sockets.TcpListener]::new(
            [System.Net.IPAddress]::Parse("127.0.0.1"),
            0
        )
        $fallbackListener.Start()
        return ([System.Net.IPEndPoint]$fallbackListener.LocalEndpoint).Port
    } finally {
        if ($fallbackListener -ne $null) {
            $fallbackListener.Stop()
        }
    }
}

$frontendPort = Get-FreePort -PreferredPort 3000
$backendPort = Get-FreePort -PreferredPort 8000
$dbPort = Get-FreePort -PreferredPort 5432
$redisPort = Get-FreePort -PreferredPort 6381
$ollamaPort = Get-FreePort -PreferredPort 11434

$envFilePath = Join-Path $PSScriptRoot ".compose-ports.env"
$envLines = @(
    "FRONTEND_HOST_PORT=$frontendPort"
    "BACKEND_HOST_PORT=$backendPort"
    "DB_HOST_PORT=$dbPort"
    "REDIS_HOST_PORT=$redisPort"
    "OLLAMA_HOST_PORT=$ollamaPort"
    "FRONTEND_PUBLIC_ORIGIN=http://127.0.0.1:$frontendPort"
    "FRONTEND_API_PUBLIC_URL=http://127.0.0.1:$backendPort"
    "NEXTAUTH_URL=http://127.0.0.1:$frontendPort"
    "NEXT_PUBLIC_API_URL=http://127.0.0.1:$backendPort"
    "BACKEND_CORS_ORIGINS=http://127.0.0.1:$frontendPort,http://localhost:$frontendPort"
)
Set-Content -Path $envFilePath -Value $envLines -Encoding ascii

Write-Host "Starting Docker stack with ports:"
Write-Host "  Frontend: http://127.0.0.1:$frontendPort"
Write-Host "  Backend:  http://127.0.0.1:$backendPort"
Write-Host "  Postgres: 127.0.0.1:$dbPort"
Write-Host "  Redis:    127.0.0.1:$redisPort"
Write-Host "  Ollama:   127.0.0.1:$ollamaPort"

docker compose --env-file $envFilePath up -d --build
