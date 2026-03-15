param(
    [string]$ConfigPath = "deploy/deploy.config.toml"
)

$ErrorActionPreference = "Stop"

function Get-Config {
    param([string]$Path)
    $json = python -c "import json, pathlib, tomllib; p=pathlib.Path(r'$Path'); print(json.dumps(tomllib.loads(p.read_text(encoding='utf-8'))))"
    if ($LASTEXITCODE -ne 0) { throw "Failed to parse config file: $Path" }
    return $json | ConvertFrom-Json
}

function Select-Name {
    param([string]$Configured, [string]$Default)
    if ([string]::IsNullOrWhiteSpace($Configured)) { return $Default }
    return $Configured
}

if (-not (Get-Command func -ErrorAction SilentlyContinue)) {
    throw "Azure Functions Core Tools (func) is required."
}

$config = Get-Config -Path $ConfigPath
$prefix = $config.naming.prefix.ToLower()
$functionAppName = Select-Name $config.naming.function_app_name "func-$prefix"
$resourceGroup = Select-Name $config.azure.resource_group_name "rg-$prefix"

if ([string]::IsNullOrWhiteSpace($config.naming.function_app_name)) {
    $detected = az functionapp list --resource-group $resourceGroup --query "[0].name" -o tsv 2>$null
    if (-not [string]::IsNullOrWhiteSpace($detected)) {
        $functionAppName = $detected
    }
}

Write-Host "[deploy-function] Publishing to $functionAppName ..."
func azure functionapp publish $functionAppName --python

# Ensure Azure management plane has the latest function trigger metadata.
$subscriptionId = $config.azure.subscription_id
if ([string]::IsNullOrWhiteSpace($subscriptionId)) {
    $subscriptionId = az account show --query id -o tsv
}
az rest --method post --uri "https://management.azure.com/subscriptions/$subscriptionId/resourceGroups/$resourceGroup/providers/Microsoft.Web/sites/$functionAppName/syncfunctiontriggers?api-version=2025-05-01" | Out-Null
Write-Host "[deploy-function] Trigger metadata sync requested."
