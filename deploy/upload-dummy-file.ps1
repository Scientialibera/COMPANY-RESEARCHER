param(
    [string]$ConfigPath = "deploy/deploy.config.toml",
    [string]$CompanyFolder = "sample_company",
    [string]$BlobName = "company_profile.json",
    [string]$InputFilePath = "deploy/assets/companies/sample_company/company_profile.json"
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

$config = Get-Config -Path $ConfigPath

$subscriptionId = $config.azure.subscription_id
if (-not [string]::IsNullOrWhiteSpace($subscriptionId)) {
    az account set --subscription $subscriptionId | Out-Null
}

$prefix = $config.naming.prefix.ToLower()
$resourceGroup = Select-Name $config.azure.resource_group_name "rg-$prefix"
$resolvedStorage = Select-Name $config.naming.storage_account_name ""

if ([string]::IsNullOrWhiteSpace($resolvedStorage)) {
    $resolvedStorage = az storage account list --resource-group $resourceGroup --query "[0].name" -o tsv 2>$null
}
if ([string]::IsNullOrWhiteSpace($resolvedStorage)) {
    throw "Could not resolve storage account name. Set naming.storage_account_name in deploy.config.toml."
}

$sourceContainer = $config.storage.source_container
if (-not (Test-Path $InputFilePath)) {
    throw "Input file not found: $InputFilePath"
}

$targetBlob = "$CompanyFolder/$BlobName"
Write-Host "[upload-dummy-file] Uploading to $resolvedStorage/$sourceContainer/$targetBlob"
az storage blob upload `
  --auth-mode login `
  --account-name $resolvedStorage `
  --container-name $sourceContainer `
  --name $targetBlob `
  --file $InputFilePath `
  --overwrite true | Out-Null

Write-Host "[upload-dummy-file] Upload complete."
