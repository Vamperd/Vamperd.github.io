$ErrorActionPreference = "Stop"
$AppRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $AppRoot

Push-Location $RepoRoot
try {
    python todo_app/server.py
}
finally {
    Pop-Location
}
