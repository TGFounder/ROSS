#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Position = 0, Mandatory = $true)]
    [ValidateSet("install", "verify", "update", "rollback", "uninstall")]
    [string]$Action,
    [string]$Source,
    [Parameter(Mandatory = $true)][string]$Target,
    [Parameter(Mandatory = $true)][string]$Version,
    [Parameter(Mandatory = $true)][string]$Sha
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Fail([string]$Message) {
    throw "FAIL: $Message"
}

function Assert-Identity([string]$Root, [string]$ExpectedVersion, [string]$ExpectedSha) {
    $releasePath = Join-Path $Root "RELEASE"
    if (-not (Test-Path -LiteralPath $releasePath -PathType Leaf)) { Fail "missing RELEASE file" }
    $values = @{}
    foreach ($line in Get-Content -LiteralPath $releasePath) {
        if ($line -notmatch '^([a-z]+)=(.+)$') { Fail "invalid RELEASE line" }
        $values[$Matches[1]] = $Matches[2]
    }
    if ($values.version -ne $ExpectedVersion) { Fail "version mismatch" }
    if ($values.tag -ne "v$ExpectedVersion") { Fail "tag mismatch" }
    if ($values.sha -ne $ExpectedSha) { Fail "SHA mismatch" }
}

function Assert-NoReparsePoint([string]$Path) {
    $item = Get-Item -LiteralPath $Path -Force
    while ($null -ne $item) {
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            Fail "path crosses a reparse point: $($item.FullName)"
        }
        $item = $item.Parent
    }
}

function Verify-Root([string]$Root, [string]$ExpectedVersion, [string]$ExpectedSha) {
    if (-not (Test-Path -LiteralPath $Root -PathType Container)) { Fail "not installed: $Root" }
    Assert-NoReparsePoint $Root
    $links = Get-ChildItem -LiteralPath $Root -Recurse -Force | Where-Object {
        ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0
    }
    if ($links) { Fail "symlink or reparse point found in ROSS directory" }
    Assert-Identity $Root $ExpectedVersion $ExpectedSha

    $manifest = Join-Path $Root "SHA256SUMS"
    if (-not (Test-Path -LiteralPath $manifest -PathType Leaf)) { Fail "missing SHA256SUMS" }
    $expected = [Collections.Generic.List[string]]::new()
    foreach ($line in Get-Content -LiteralPath $manifest) {
        if ($line -notmatch '^([0-9a-f]{64})  (.+)$') { Fail "invalid checksum line" }
        $hash = $Matches[1]
        $relative = $Matches[2]
        if ([IO.Path]::IsPathRooted($relative) -or $relative -match '\\' -or
            $relative.Split('/') -contains '..' -or $relative -eq "SHA256SUMS") {
            Fail "unsafe checksum path: $relative"
        }
        $file = Join-Path $Root $relative
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { Fail "missing file: $relative" }
        $found = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($found -ne $hash) { Fail "changed file: $relative" }
        $expected.Add($relative)
    }
    $expected.Add("SHA256SUMS")
    if (($expected | Sort-Object -Unique).Count -ne $expected.Count) { Fail "duplicate checksum path" }
    $rootPrefix = $Root.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    $actual = @(Get-ChildItem -LiteralPath $Root -File -Recurse -Force | ForEach-Object {
        $_.FullName.Substring($rootPrefix.Length).Replace('\', '/')
    })
    $difference = Compare-Object ($expected | Sort-Object) ($actual | Sort-Object)
    if ($difference) { Fail "unexpected or missing files: $($difference | Out-String)" }
    Write-Output "PASS: $Root (v$ExpectedVersion $ExpectedSha)"
}

if ($Version -notmatch '^[0-9]+\.[0-9]+\.[0-9]+$') { Fail "version must use X.Y.Z" }
if ($Sha -notmatch '^[0-9a-f]{40}$') { Fail "sha must be a full lowercase 40-character hexadecimal commit SHA" }
if (-not [IO.Path]::IsPathRooted($Target)) { Fail "target must be absolute" }
$Target = [IO.Path]::GetFullPath($Target).TrimEnd([IO.Path]::DirectorySeparatorChar)
if ([IO.Path]::GetFileName($Target) -ne "ross") { Fail "target final component must be exactly ross" }
$parent = Split-Path -Parent $Target
if (-not (Test-Path -LiteralPath $parent -PathType Container)) { Fail "target parent must exist" }
Assert-NoReparsePoint $parent
if ($parent -eq [IO.Path]::GetPathRoot($parent)) { Fail "target parent must not be a filesystem root" }
if ((Test-Path -LiteralPath $Target) -and
    (((Get-Item -LiteralPath $Target -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
    Fail "target must not be a reparse point"
}

if ($Action -eq "verify") {
    Verify-Root $Target $Version $Sha
    exit 0
}

if ($Action -eq "uninstall") {
    Verify-Root $Target $Version $Sha | Out-Null
    Remove-Item -LiteralPath $Target -Recurse -Force
    Write-Output "PASS: uninstalled $Target; neighboring files were not selected"
    exit 0
}

if ([string]::IsNullOrWhiteSpace($Source)) { Fail "source is required" }
$Source = [IO.Path]::GetFullPath($Source).TrimEnd([IO.Path]::DirectorySeparatorChar)
if (-not (Test-Path -LiteralPath $Source -PathType Container)) { Fail "source must be a directory" }
Assert-NoReparsePoint $Source
if ($Source -eq $Target) { Fail "source and target must differ" }
Verify-Root $Source $Version $Sha | Out-Null

$stage = Join-Path $parent ".ross-stage.$([guid]::NewGuid().ToString('N'))"
New-Item -ItemType Directory -Path $stage | Out-Null
try {
    Get-ChildItem -LiteralPath $Source -Force | Copy-Item -Destination $stage -Recurse -Force
    Verify-Root $stage $Version $Sha | Out-Null
    if ($Action -eq "install") {
        if (Test-Path -LiteralPath $Target) { Fail "ROSS target already exists" }
        Move-Item -LiteralPath $stage -Destination $Target
    } else {
        if (-not (Test-Path -LiteralPath $Target -PathType Container)) { Fail "existing ROSS installation is required" }
        $currentRelease = @{}
        foreach ($line in Get-Content -LiteralPath (Join-Path $Target "RELEASE")) {
            if ($line -match '^([a-z]+)=(.+)$') { $currentRelease[$Matches[1]] = $Matches[2] }
        }
        Verify-Root $Target $currentRelease.version $currentRelease.sha | Out-Null
        $backup = Join-Path $parent ".ross-backup.$([guid]::NewGuid().ToString('N'))"
        Move-Item -LiteralPath $Target -Destination $backup
        try {
            Move-Item -LiteralPath $stage -Destination $Target
            Verify-Root $Target $Version $Sha | Out-Null
            Remove-Item -LiteralPath $backup -Recurse -Force
        } catch {
            if (Test-Path -LiteralPath $Target) { Remove-Item -LiteralPath $Target -Recurse -Force }
            if (Test-Path -LiteralPath $backup) { Move-Item -LiteralPath $backup -Destination $Target }
            throw
        }
    }
    Verify-Root $Target $Version $Sha | Out-Null
    Write-Output "PASS: $Action v$Version at $Target"
} finally {
    if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
}
