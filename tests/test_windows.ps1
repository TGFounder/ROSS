$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$TempRoot = Join-Path ([IO.Path]::GetTempPath()) "ross-windows.$([guid]::NewGuid().ToString('N'))"
$Version = "1.0.0"
$Sha = (git -C $Root rev-parse HEAD).Trim()

try {
    New-Item -ItemType Directory -Path $TempRoot | Out-Null
    python (Join-Path $Root "scripts/package.py") --source $Root --output (Join-Path $TempRoot "one") --version $Version --sha $Sha | Out-Null
    python (Join-Path $Root "scripts/package.py") --source $Root --output (Join-Path $TempRoot "two") --version $Version --sha $Sha | Out-Null
    $zipOne = Join-Path $TempRoot "one/ross-v$Version.zip"
    $zipTwo = Join-Path $TempRoot "two/ross-v$Version.zip"
    if ((Get-FileHash $zipOne -Algorithm SHA256).Hash -ne (Get-FileHash $zipTwo -Algorithm SHA256).Hash) {
        throw "packages are not reproducible"
    }

    $Extracted = Join-Path $TempRoot "extracted"
    $Skills = Join-Path $TempRoot "skills"
    New-Item -ItemType Directory -Path $Extracted, $Skills | Out-Null
    Expand-Archive -LiteralPath $zipOne -DestinationPath $Extracted
    Set-Content -LiteralPath (Join-Path $Skills "unrelated.txt") -Value "keep"
    $Lifecycle = Join-Path $Extracted "ross/scripts/ross.ps1"
    $Target = Join-Path $Skills "ross"

    & $Lifecycle install -Source (Join-Path $Extracted "ross") -Target $Target -Version $Version -Sha $Sha | Out-Null
    & $Lifecycle verify -Target $Target -Version $Version -Sha $Sha | Out-Null
    try {
        & $Lifecycle install -Source (Join-Path $Extracted "ross") -Target $Target -Version $Version -Sha $Sha | Out-Null
        throw "existing installation was overwritten"
    } catch {
        if ($_.Exception.Message -eq "existing installation was overwritten") { throw }
    }

    Add-Content -LiteralPath (Join-Path $Target "SKILL.md") -Value "tampered"
    try {
        & $Lifecycle verify -Target $Target -Version $Version -Sha $Sha | Out-Null
        throw "changed file was not detected"
    } catch {
        if ($_.Exception.Message -eq "changed file was not detected") { throw }
    }
    Copy-Item -LiteralPath (Join-Path $Extracted "ross/SKILL.md") -Destination (Join-Path $Target "SKILL.md") -Force
    Set-Content -LiteralPath (Join-Path $Target "EXTRA") -Value "extra"
    try {
        & $Lifecycle verify -Target $Target -Version $Version -Sha $Sha | Out-Null
        throw "unexpected file was not detected"
    } catch {
        if ($_.Exception.Message -eq "unexpected file was not detected") { throw }
    }
    Remove-Item -LiteralPath (Join-Path $Target "EXTRA")
    New-Item -ItemType Directory -Path (Join-Path $Target "EMPTY") | Out-Null
    try {
        & $Lifecycle verify -Target $Target -Version $Version -Sha $Sha | Out-Null
        throw "unexpected empty directory was not detected"
    } catch {
        if ($_.Exception.Message -eq "unexpected empty directory was not detected") { throw }
    }
    Remove-Item -LiteralPath (Join-Path $Target "EMPTY")

    & $Lifecycle update -Source (Join-Path $Extracted "ross") -Target $Target -Version $Version -Sha $Sha | Out-Null
    & $Lifecycle rollback -Source (Join-Path $Extracted "ross") -Target $Target -Version $Version -Sha $Sha | Out-Null

    $LinkedSource = Join-Path $TempRoot "linked-source"
    Copy-Item -LiteralPath (Join-Path $Extracted "ross") -Destination $LinkedSource -Recurse
    $JunctionTarget = Join-Path $TempRoot "junction-target"
    New-Item -ItemType Directory -Path $JunctionTarget | Out-Null
    New-Item -ItemType Junction -Path (Join-Path $LinkedSource "bad-link") -Target $JunctionTarget | Out-Null
    try {
        & $Lifecycle update -Source $LinkedSource -Target $Target -Version $Version -Sha $Sha | Out-Null
        throw "reparse-point source was accepted"
    } catch {
        if ($_.Exception.Message -eq "reparse-point source was accepted") { throw }
    }

    & $Lifecycle uninstall -Target $Target -Version $Version -Sha $Sha | Out-Null
    if (Test-Path -LiteralPath $Target) { throw "ROSS target remains after uninstall" }
    if ((Get-Content -LiteralPath (Join-Path $Skills "unrelated.txt")) -ne "keep") { throw "neighboring file changed" }
    Write-Output "PASS: Windows package and lifecycle isolation"
} finally {
    if (Test-Path -LiteralPath $TempRoot) { Remove-Item -LiteralPath $TempRoot -Recurse -Force }
}
