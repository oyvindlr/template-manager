# Reference contract for a .NET/WiX service template; configure the paths in its TOML contract.
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Output,
    [Parameter(Mandatory)][string]$InstallerProject,
    [Parameter(Mandatory)][string]$PublishDirectory,
    [Parameter(Mandatory)][string]$MsiPattern,
    [string]$RuntimeIdentifier = 'win-x64'
)
$ErrorActionPreference = 'Stop'
Set-Location $Output
function Invoke-Dotnet([string[]]$Arguments) {
    & dotnet @Arguments
    if ($LASTEXITCODE -ne 0) { throw "dotnet failed: $Arguments" }
}
# Fresh output is supplied by test-template/validate. The installer target must
# remove stale publish files itself; the test intentionally does not clean them.
New-Item -ItemType Directory -Force $PublishDirectory | Out-Null
$stale = Join-Path $PublishDirectory 'reverse-sync-stale-file.txt'
Set-Content $stale 'must be removed by the publish target'
Invoke-Dotnet -Arguments @('restore', $InstallerProject, '-r', $RuntimeIdentifier, '-p:Platform=x64')
Invoke-Dotnet -Arguments @('build', $InstallerProject, '--no-restore', '-c', 'Release',
    '-p:Platform=x64', "-p:RuntimeIdentifier=$RuntimeIdentifier", '-p:SelfContained=false')
if (Test-Path $stale) { throw 'Publish target retained stale output' }
if (-not (Get-ChildItem -Path $MsiPattern -File)) { throw 'MSI was not produced' }
if (Get-ChildItem $PublishDirectory -Filter hostfxr.dll -Recurse) {
    throw 'Framework-dependent output unexpectedly contains hostfxr.dll'
}
# Add focused application tests here when the template has them.
