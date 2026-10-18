[CmdletBinding()]
param(
    [string]$PythonPath,
    [string]$Server = 'localhost',
    [string]$Infobase = 'UTrecover',
    [string]$CredentialPath,
    [switch]$Discover,
    [switch]$AuditReference,
    [int]$SampleSize = 4
)
$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
if (-not $CredentialPath) {
    $CredentialPath = Join-Path $projectRoot 'data\trade-harness\credential.xml'
}
if (-not $PythonPath) {
    $localPython = Join-Path (Split-Path $projectRoot -Parent) '.python\python.exe'
    if (Test-Path -LiteralPath $localPython) { $PythonPath = $localPython }
    else { $PythonPath = (Get-Command python -ErrorAction Stop).Source }
}
$previous = @{}
foreach ($name in @('CTM_UT_PASSWORD', 'CTM_UT_USER', 'CTM_UT_HOST', 'CTM_UT_INFOBASE')) {
    $previous[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
try {
    if (-not $env:CTM_UT_PASSWORD) {
        if (-not (Test-Path -LiteralPath $CredentialPath)) {
            throw 'Missing local credential. Set CTM_UT_PASSWORD/CTM_UT_USER or create the DPAPI credential described in TRADE_ACCRUAL_HARNESS.md.'
        }
        $credential = Import-Clixml -LiteralPath $CredentialPath
        if ($credential -isnot [System.Management.Automation.PSCredential]) {
            throw 'Expected a Windows DPAPI-protected PSCredential file.'
        }
        $env:CTM_UT_USER = $credential.UserName
        $env:CTM_UT_PASSWORD = $credential.GetNetworkCredential().Password
    }
    $env:CTM_UT_HOST = $Server
    $env:CTM_UT_INFOBASE = $Infobase
    $arguments = @('-X', 'utf8', (Join-Path $PSScriptRoot 'reconcile.py'))
    if ($AuditReference) {
        if ($Discover) { throw 'AuditReference and Discover cannot be combined.' }
        $arguments = @('-X', 'utf8', (Join-Path $PSScriptRoot 'suite.py'), 'audit-reference',
                       '--report', (Join-Path $projectRoot 'data\trade-harness\reference-audit.json'))
    }
    if ($Discover) { $arguments += @('--discover', '--sample-size', "$SampleSize") }
    & $PythonPath @arguments
    $resultCode = $LASTEXITCODE
}
finally {
    foreach ($name in $previous.Keys) {
        [Environment]::SetEnvironmentVariable($name, $previous[$name], 'Process')
    }
}
exit $resultCode
