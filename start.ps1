param([ValidateRange(1,16)][int]$Replicas = 1)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path .env)) {
    $bytes = New-Object byte[] 24
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $passwordValue = ([BitConverter]::ToString($bytes)).Replace('-','').ToLower()
    "POSTGRES_PASSWORD=$passwordValue`nPOSTGRES_USER=vaccinations`nPOSTGRES_DB=vaccinations`nPORT=18080" | Set-Content .env -Encoding ascii
}
$dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
if ($dockerCommand) { $dockerCli = $dockerCommand.Source }
elseif (Test-Path "$env:LOCALAPPDATA/Programs/DockerDesktop/resources/bin/docker.exe") { $dockerCli = "$env:LOCALAPPDATA/Programs/DockerDesktop/resources/bin/docker.exe" }
elseif (Test-Path 'C:/Program Files/Docker/Docker/resources/bin/docker.exe') { $dockerCli = 'C:/Program Files/Docker/Docker/resources/bin/docker.exe' }
else { throw 'Install Docker Desktop and start its Linux Engine first.' }
& $dockerCli compose up -d --build --wait --scale "web=$Replicas"
if ($LASTEXITCODE -ne 0) { throw 'Docker Compose failed' }
