param(
    [string]$ConfigPath = "deploy/deploy.config.toml"
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

function Write-Step {
    param([string]$Message)
    Write-Host "[deploy-function] $Message"
}

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

function Ensure-RoleAssignment {
    param(
        [string]$PrincipalId,
        [string]$Scope,
        [string]$Role,
        [string]$PrincipalType = "User"
    )
    $count = az role assignment list `
      --assignee-object-id $PrincipalId `
      --scope $Scope `
      --query "[?roleDefinitionName=='$Role'] | length(@)" `
      -o tsv
    if ($LASTEXITCODE -ne 0) { throw "Failed to query role assignments for '$Role'." }
    if ($count -eq "0") {
        Write-Step "Assigning role '$Role' on scope '$Scope'."
        az role assignment create `
          --assignee-object-id $PrincipalId `
          --assignee-principal-type $PrincipalType `
          --role $Role `
          --scope $Scope | Out-Null
    }
}

function Upload-BlobFromFile {
    param(
        [string]$StorageAccount,
        [string]$Container,
        [string]$BlobName,
        [string]$FilePath
    )
    if (-not (Test-Path $FilePath)) {
        throw "Required deployment asset not found: $FilePath"
    }
    az storage blob upload `
      --auth-mode login `
      --account-name $StorageAccount `
      --container-name $Container `
      --name $BlobName `
      --file $FilePath `
      --overwrite true | Out-Null
}

function Normalize-StorageAccountName {
    param([string]$Value)
    $normalized = ($Value.ToLower() -replace "[^a-z0-9]", "")
    if ([string]::IsNullOrWhiteSpace($normalized)) {
        throw "Invalid prefix for storage account generation."
    }
    if ($normalized.Length -lt 3) {
        $normalized = $normalized + "123"
    }
    if ($normalized.Length -gt 22) {
        $normalized = $normalized.Substring(0, 22)
    }
    return "st$normalized"
}

function Ensure-ProviderRegistered {
    param([string]$Namespace)
    $state = az provider show --namespace $Namespace --query registrationState -o tsv 2>$null
    if ($state -eq "Registered") {
        return
    }

    Write-Step "Registering provider '$Namespace'."
    az provider register --namespace $Namespace | Out-Null
    $deadline = (Get-Date).AddMinutes(10)
    do {
        Start-Sleep -Seconds 10
        $state = az provider show --namespace $Namespace --query registrationState -o tsv 2>$null
        if ($state -eq "Registered") {
            return
        }
    } while ((Get-Date) -lt $deadline)

    throw "Provider '$Namespace' registration did not complete in time."
}

function Ensure-FunctionIndexed {
    param(
        [string]$SubscriptionId,
        [string]$ResourceGroup,
        [string]$FunctionAppName,
        [string]$FunctionName
    )

    $expected = "$FunctionAppName/$FunctionName"
    $deadline = (Get-Date).AddMinutes(6)
    do {
        $functions = az functionapp function list `
          --resource-group $ResourceGroup `
          --name $FunctionAppName `
          --query "[].name" -o tsv 2>$null
        if ($functions -and ($functions -split "`n" | Where-Object { $_ -eq $expected })) {
            return
        }

        az rest --method post --uri "https://management.azure.com/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Web/sites/$FunctionAppName/syncfunctiontriggers?api-version=2025-05-01" | Out-Null
        Start-Sleep -Seconds 10
    } while ((Get-Date) -lt $deadline)

    throw "Function '$expected' was not indexed after trigger sync retries."
}

function Ensure-EventSubscriptionAzureFunction {
    param(
        [string]$SourceResourceId,
        [string]$EventSubscriptionName,
        [string]$SubjectBeginsWith,
        [string]$SubjectEndsWith,
        [string]$FunctionResourceId
    )

    $deadline = (Get-Date).AddMinutes(5)
    do {
        az eventgrid event-subscription create `
          --name $EventSubscriptionName `
          --source-resource-id $SourceResourceId `
          --included-event-types Microsoft.Storage.BlobCreated `
          --subject-begins-with $SubjectBeginsWith `
          --subject-ends-with $SubjectEndsWith `
          --endpoint-type azurefunction `
          --endpoint $FunctionResourceId | Out-Null
        if ($LASTEXITCODE -eq 0) {
            return
        }
        Start-Sleep -Seconds 10
    } while ((Get-Date) -lt $deadline)

    throw "Failed to create Event Grid subscription '$EventSubscriptionName' with Azure Function endpoint."
}

if (-not (Get-Command func -ErrorAction SilentlyContinue)) {
    throw "Azure Functions Core Tools (func) is required."
}

$config = Get-Config -Path $ConfigPath
$prefix = $config.naming.prefix.ToLower()
$functionAppName = Select-Name $config.naming.function_app_name "func-$prefix"
$resourceGroup = Select-Name $config.azure.resource_group_name "rg-$prefix"
$storageAccount = Select-Name $config.naming.storage_account_name (Normalize-StorageAccountName -Value $prefix)
$sourceContainer = $config.storage.source_container
$appConfigPath = $config.app_settings.app_config_path
$appConfigJson = python -c "import json, pathlib, tomllib; p=pathlib.Path(r'$appConfigPath'); print(json.dumps(tomllib.loads(p.read_text(encoding='utf-8'))))"
if ($LASTEXITCODE -ne 0) { throw "Failed to parse app config file: $appConfigPath" }
$runtimeConfig = $appConfigJson | ConvertFrom-Json
$indicatorFileName = $runtimeConfig.storage.indicator_file_name
$ourCompanyProfileBlobName = $runtimeConfig.context.our_company_profile_blob_name
$researchPromptBlobName = $runtimeConfig.agents.research.system_prompt_blob_name
$strategyPromptBlobName = $runtimeConfig.agents.strategy.system_prompt_blob_name
$functionDefinitionBlobName = $runtimeConfig.function_call.definition_blob_name
$additionalContainer = $config.storage.additional_container
$promptsContainer = $config.storage.prompts_container
$functionDefinitionsContainer = $config.storage.function_definitions_container
$assetsRoot = Join-Path $PSScriptRoot "assets"
$ourCompanyProfileAssetPath = Join-Path $assetsRoot "shared/our_company_profile.txt"
$researchPromptAssetPath = Join-Path $assetsRoot "prompts/research/system_prompt.txt"
$strategyPromptAssetPath = Join-Path $assetsRoot "prompts/strategy/system_prompt.txt"
$functionDefinitionAssetPath = Join-Path $assetsRoot "function_definitions/sales/sales_strategy_function.json"

if ([string]::IsNullOrWhiteSpace($config.naming.function_app_name)) {
    $detected = az functionapp list --resource-group $resourceGroup --query "[0].name" -o tsv 2>$null
    if (-not [string]::IsNullOrWhiteSpace($detected)) {
        $functionAppName = $detected
    }
}

if ([string]::IsNullOrWhiteSpace($config.naming.storage_account_name)) {
    $detectedStorage = az storage account list --resource-group $resourceGroup --query "[0].name" -o tsv 2>$null
    if (-not [string]::IsNullOrWhiteSpace($detectedStorage)) {
        $storageAccount = $detectedStorage
    }
}

Write-Step "Publishing to $functionAppName ..."
func azure functionapp publish $functionAppName --python

Write-Step "Ensuring executor blob data role for asset seeding."
$executorObjectId = az ad signed-in-user show --query id -o tsv
$storageScope = az storage account show --resource-group $resourceGroup --name $storageAccount --query id -o tsv
Ensure-RoleAssignment -PrincipalId $executorObjectId -Scope $storageScope -Role "Storage Blob Data Owner"

Write-Step "Seeding runtime blobs."
Upload-BlobFromFile -StorageAccount $storageAccount -Container $additionalContainer -BlobName $ourCompanyProfileBlobName -FilePath $ourCompanyProfileAssetPath
Upload-BlobFromFile -StorageAccount $storageAccount -Container $promptsContainer -BlobName $researchPromptBlobName -FilePath $researchPromptAssetPath
Upload-BlobFromFile -StorageAccount $storageAccount -Container $promptsContainer -BlobName $strategyPromptBlobName -FilePath $strategyPromptAssetPath
Upload-BlobFromFile -StorageAccount $storageAccount -Container $functionDefinitionsContainer -BlobName $functionDefinitionBlobName -FilePath $functionDefinitionAssetPath

# Ensure Azure management plane has the latest function trigger metadata.
$subscriptionId = $config.azure.subscription_id
if ([string]::IsNullOrWhiteSpace($subscriptionId)) {
    $subscriptionId = az account show --query id -o tsv
}
az account set --subscription $subscriptionId | Out-Null
az rest --method post --uri "https://management.azure.com/subscriptions/$subscriptionId/resourceGroups/$resourceGroup/providers/Microsoft.Web/sites/$functionAppName/syncfunctiontriggers?api-version=2025-05-01" | Out-Null
Write-Step "Trigger metadata sync requested."

Write-Step "Ensuring Event Grid provider and subscription."
Ensure-ProviderRegistered -Namespace "Microsoft.EventGrid"
Ensure-FunctionIndexed `
  -SubscriptionId $subscriptionId `
  -ResourceGroup $resourceGroup `
  -FunctionAppName $functionAppName `
  -FunctionName "CompanyResearchBlobTrigger"

$sourceResourceId = az storage account show `
  --name $storageAccount `
  --resource-group $resourceGroup `
  --query id -o tsv
$eventSubName = "evg-source-indicator-created"
$eventSubCount = az eventgrid event-subscription list `
  --source-resource-id $sourceResourceId `
  --query "[?name=='$eventSubName'] | length(@)" -o tsv

$functionResourceId = "/subscriptions/$subscriptionId/resourceGroups/$resourceGroup/providers/Microsoft.Web/sites/$functionAppName/functions/CompanyResearchBlobTrigger"
if ($eventSubCount -ne "0") {
    az eventgrid event-subscription delete `
      --name $eventSubName `
      --source-resource-id $sourceResourceId | Out-Null
    Start-Sleep -Seconds 5
}

Ensure-EventSubscriptionAzureFunction `
  -SourceResourceId $sourceResourceId `
  -EventSubscriptionName $eventSubName `
  -SubjectBeginsWith "/blobServices/default/containers/$sourceContainer/blobs/" `
  -SubjectEndsWith $indicatorFileName `
  -FunctionResourceId $functionResourceId

Write-Step "Event Grid subscription ensured."
