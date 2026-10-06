<#
.SYNOPSIS
    Start / stop / check the local Postgres 16 that lives in D:\pg (outside Temp, so
    Windows temp cleanup can't delete it).

.DESCRIPTION
    Layout:  D:\pg\pgsql   portable EDB binaries (bin, lib, share)
             D:\pg\pgdata  data directory (cropcast + cropcast_test databases)
             D:\pg\pg.log  server log
    Auth is `trust` for local connections; user `cropcast`.
    Override the root with $env:CROPCAST_PG_ROOT.

.EXAMPLE
    .\scripts\pg_local.ps1 start
    .\scripts\pg_local.ps1 status
    .\scripts\pg_local.ps1 check     # status + row counts
    .\scripts\pg_local.ps1 stop
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("start", "stop", "restart", "status", "check")]
    [string]$Command,
    [int]$Port = 5432
)

$ErrorActionPreference = "Stop"
$Root = if ($env:CROPCAST_PG_ROOT) { $env:CROPCAST_PG_ROOT } else { "D:\pg" }
$Bin = Join-Path $Root "pgsql\bin"
$Data = Join-Path $Root "pgdata"
$Log = Join-Path $Root "pg.log"
$PgCtl = Join-Path $Bin "pg_ctl.exe"
$Psql = Join-Path $Bin "psql.exe"

foreach ($p in @($PgCtl, $Psql, (Join-Path $Data "PG_VERSION"))) {
    if (-not (Test-Path $p)) { throw "Missing $p - is Postgres installed under $Root?" }
}

function Get-Status {
    & $PgCtl -D $Data status | Out-Host
    return $LASTEXITCODE  # 0 = running, 3 = not running
}

function Start-Pg {
    if ((Get-Status) -eq 0) { Write-Host "already running"; return }
    & $PgCtl -D $Data -l $Log -o "-p $Port" -w -t 60 start
    if ($LASTEXITCODE -ne 0) { throw "pg_ctl start failed - see $Log" }
}

function Stop-Pg {
    if ((Get-Status) -ne 0) { Write-Host "not running"; return }
    & $PgCtl -D $Data -m fast -w -t 60 stop
    if ($LASTEXITCODE -ne 0) { throw "pg_ctl stop failed - see $Log" }
}

switch ($Command) {
    "start" { Start-Pg }
    "stop" { Stop-Pg }
    "restart" { Stop-Pg; Start-Pg }
    "status" { [void](Get-Status) }
    "check" {
        if ((Get-Status) -ne 0) { throw "server not running" }
        & $Psql -h localhost -p $Port -U cropcast -d cropcast -c @"
select (select count(*) from prices_raw)      as prices_raw,
       (select count(*) from prices_rejected) as prices_rejected,
       (select count(*) from weather_daily)   as weather_daily,
       (select count(*) from pipeline_runs)   as pipeline_runs
"@
    }
}
