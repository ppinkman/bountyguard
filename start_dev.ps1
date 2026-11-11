param(
    [int]$Port = 8766,
    [switch]$UseGitHubLogin,
    [switch]$UseExistingAiCredits,
    [string]$AiKeyFile,
    [switch]$EnableTestnet,
    [switch]$DirectNetwork,
    [ValidateRange(2,4)][int]$FundingIntentLimit = 2,
    [ValidateRange(3,6)][int]$ModelIntentLimit = 3
)
$ErrorActionPreference = 'Stop'
$taskNames = @('GITHUB_TOKEN','NEAR_AI_API_KEY','BOUNTYGUARD_LOCAL_GITHUB','BOUNTYGUARD_ENABLE_AI','BOUNTYGUARD_ENABLE_TESTNET','BOUNTYGUARD_CONTRACT','BOUNTYGUARD_CODE_HASH','BOUNTYGUARD_VAULT','BOUNTYGUARD_DIRECT_NETWORK','BOUNTYGUARD_FUNDING_INTENT_LIMIT','BOUNTYGUARD_MODEL_INTENT_LIMIT','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY')
$taskPrevious = @{}
foreach ($taskName in $taskNames) { $taskPrevious[$taskName] = [Environment]::GetEnvironmentVariable($taskName,'Process') }
$taskSecureKey = $null
$taskPointer = [IntPtr]::Zero
Push-Location -LiteralPath $PSScriptRoot
try {
    $env:BOUNTYGUARD_FUNDING_INTENT_LIMIT=[string]$FundingIntentLimit
    $env:BOUNTYGUARD_MODEL_INTENT_LIMIT=[string]$ModelIntentLimit
    if ($DirectNetwork) {
        $env:BOUNTYGUARD_DIRECT_NETWORK='1'
        $env:NO_PROXY='*'
        $env:HTTP_PROXY=$null; $env:HTTPS_PROXY=$null; $env:ALL_PROXY=$null
    }
    if ($UseGitHubLogin) {
        $env:GITHUB_TOKEN = (& gh auth token 2>$null)
        if ($LASTEXITCODE -ne 0 -or -not $env:GITHUB_TOKEN) { throw 'The local GitHub login is unavailable.' }
        $env:BOUNTYGUARD_LOCAL_GITHUB='1'
    }
    if ($UseExistingAiCredits) {
        if (-not $env:NEAR_AI_API_KEY) {
            if (-not $AiKeyFile -or -not (Test-Path -LiteralPath $AiKeyFile -PathType Leaf)) { throw 'Set NEAR_AI_API_KEY or provide -AiKeyFile with an encrypted provider key.' }
            $taskSecureKey = ConvertTo-SecureString -String ([IO.File]::ReadAllText((Resolve-Path -LiteralPath $AiKeyFile).Path))
            $taskPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($taskSecureKey)
            $env:NEAR_AI_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($taskPointer)
        }
        $env:BOUNTYGUARD_ENABLE_AI='1'
    } else { $env:BOUNTYGUARD_ENABLE_AI='0' }
    $env:BOUNTYGUARD_ENABLE_TESTNET = $(if ($EnableTestnet) { '1' } else { '0' })
    if ($EnableTestnet) {
        $taskDeployment = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'data\testnet\deployment.json') -Raw | ConvertFrom-Json
        $env:BOUNTYGUARD_CONTRACT=$taskDeployment.contract
        $env:BOUNTYGUARD_CODE_HASH=$taskDeployment.code_hash
        $env:BOUNTYGUARD_VAULT=Join-Path $PSScriptRoot 'data\testnet\maintainer.dpapi'
    }
    Write-Host "BountyGuard: http://127.0.0.1:$Port/"
    Write-Host "Ready. Limits: $FundingIntentLimit funding intents; $ModelIntentLimit model intents per rolling day. Existing usage is retained."
    & (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') -m bountyguard serve --port $Port
} finally {
    if ($taskPointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($taskPointer) }
    if ($null -ne $taskSecureKey) { $taskSecureKey.Dispose() }
    foreach ($taskName in $taskNames) { [Environment]::SetEnvironmentVariable($taskName,$taskPrevious[$taskName],'Process') }
    Pop-Location
}
