param(
    [string]$ConfigPath = "deploy/deploy.config.toml"
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

function Write-Step {
    param([string]$Message)
    Write-Host "[deploy-infra] $Message"
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

function Ensure-RoleAssignment {
    param(
        [string]$PrincipalId,
        [string]$Scope,
        [string]$Role,
        [string]$PrincipalType = "ServicePrincipal"
    )

    $count = az role assignment list `
      --assignee-object-id $PrincipalId `
      --scope $Scope `
      --query "[?roleDefinitionName=='$Role'] | length(@)" `
      -o tsv
    if ($LASTEXITCODE -ne 0) { throw "Failed to query role assignments for $Role." }

    if ($count -eq "0") {
        Write-Step "Assigning role '$Role' on scope '$Scope'."
        az role assignment create `
          --assignee-object-id $PrincipalId `
          --assignee-principal-type $PrincipalType `
          --role $Role `
          --scope $Scope | Out-Null
    } else {
        Write-Step "Role '$Role' already assigned."
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
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to upload blob '$BlobName' to container '$Container'."
    }
}

if (-not (Test-Path $ConfigPath)) {
    throw "Config file not found: $ConfigPath"
}

$config = Get-Config -Path $ConfigPath

$subscriptionId = $config.azure.subscription_id
if ([string]::IsNullOrWhiteSpace($subscriptionId)) {
    $subscriptionId = az account show --query id -o tsv
}
if ([string]::IsNullOrWhiteSpace($subscriptionId)) {
    throw "No Azure subscription id found. Set deploy.config.toml azure.subscription_id or run 'az login'."
}

$location = $config.azure.location
$prefix = $config.naming.prefix.ToLower()
$resourceGroup = Select-Name $config.azure.resource_group_name "rg-$prefix"
$storageAccount = Select-Name $config.naming.storage_account_name (Normalize-StorageAccountName -Value $prefix)
$functionAppName = Select-Name $config.naming.function_app_name "func-$prefix"
$openAIAccount = Select-Name $config.naming.openai_account_name "aoai-$prefix"
$defaultAppInsightsName = "appi-$prefix"

$sourceContainer = $config.storage.source_container
$sinkContainer = $config.storage.sink_container
$additionalContainer = $config.storage.additional_container
$promptsContainer = $config.storage.prompts_container
$functionDefinitionsContainer = $config.storage.function_definitions_container
$appConfigPath = $config.app_settings.app_config_path
$assetsRoot = Join-Path $PSScriptRoot "assets"
$appConfigJson = python -c "import json, pathlib, tomllib; p=pathlib.Path(r'$appConfigPath'); print(json.dumps(tomllib.loads(p.read_text(encoding='utf-8'))))"
if ($LASTEXITCODE -ne 0) { throw "Failed to parse app config file: $appConfigPath" }
$runtimeConfig = $appConfigJson | ConvertFrom-Json
$ourCompanyProfileBlobName = $runtimeConfig.context.our_company_profile_blob_name
$researchPromptBlobName = $runtimeConfig.agents.research.system_prompt_blob_name
$strategyPromptBlobName = $runtimeConfig.agents.strategy.system_prompt_blob_name
$functionDefinitionBlobName = $runtimeConfig.function_call.definition_blob_name
$indicatorFileName = $runtimeConfig.storage.indicator_file_name
$ourCompanyProfileAssetPath = Join-Path $assetsRoot "shared/our_company_profile.txt"
$researchPromptAssetPath = Join-Path $assetsRoot "prompts/research/system_prompt.txt"
$strategyPromptAssetPath = Join-Path $assetsRoot "prompts/strategy/system_prompt.txt"
$functionDefinitionAssetPath = Join-Path $assetsRoot "function_definitions/sales/sales_strategy_function.json"

Write-Step "Using subscription: $subscriptionId"
az account set --subscription $subscriptionId

Write-Step "Ensuring resource group '$resourceGroup'."
$rgExists = az group exists --name $resourceGroup -o tsv
if ($rgExists -ne "true") {
    az group create --name $resourceGroup --location $location | Out-Null
}
$resourceGroupScope = az group show --name $resourceGroup --query id -o tsv

Write-Step "Ensuring script executor roles on resource group."
$executorObjectId = az ad signed-in-user show --query id -o tsv
if ([string]::IsNullOrWhiteSpace($executorObjectId)) {
    throw "Could not resolve signed-in user object id from Azure CLI."
}
Ensure-RoleAssignment -PrincipalId $executorObjectId -PrincipalType User -Scope $resourceGroupScope -Role "Contributor"

Write-Step "Ensuring storage account '$storageAccount'."
$storageExistsCount = az storage account list --resource-group $resourceGroup --query "[?name=='$storageAccount'] | length(@)" -o tsv
if ($storageExistsCount -eq "0") {
    az storage account create `
      --name $storageAccount `
      --resource-group $resourceGroup `
      --location $location `
      --sku Standard_LRS `
      --kind StorageV2 | Out-Null
}

$storageScope = az storage account show --resource-group $resourceGroup --name $storageAccount --query id -o tsv
Write-Step "Ensuring script executor storage data-plane role."
Ensure-RoleAssignment -PrincipalId $executorObjectId -PrincipalType User -Scope $storageScope -Role "Storage Blob Data Owner"

foreach ($container in @($sourceContainer, $sinkContainer, $additionalContainer, $promptsContainer)) {
    Write-Step "Ensuring container '$container'."
    $existsRaw = az storage container exists `
      --account-name $storageAccount `
      --name $container `
      --auth-mode login `
      --query exists -o tsv
    if ($existsRaw -ne "true") {
        az storage container create `
          --account-name $storageAccount `
          --name $container `
          --auth-mode login | Out-Null
    }
}

Write-Step "Uploading shared our-company profile blob '$ourCompanyProfileBlobName'."
Upload-BlobFromFile `
  -StorageAccount $storageAccount `
  -Container $additionalContainer `
  -BlobName $ourCompanyProfileBlobName `
  -FilePath $ourCompanyProfileAssetPath

Write-Step "Uploading research prompt blob '$researchPromptBlobName'."
Upload-BlobFromFile `
  -StorageAccount $storageAccount `
  -Container $promptsContainer `
  -BlobName $researchPromptBlobName `
  -FilePath $researchPromptAssetPath

Write-Step "Uploading strategy prompt blob '$strategyPromptBlobName'."
Upload-BlobFromFile `
  -StorageAccount $storageAccount `
  -Container $promptsContainer `
  -BlobName $strategyPromptBlobName `
  -FilePath $strategyPromptAssetPath

Write-Step "Ensuring function-definitions container '$functionDefinitionsContainer'."
$functionDefContainerExists = az storage container exists `
  --account-name $storageAccount `
  --name $functionDefinitionsContainer `
  --auth-mode login `
  --query exists -o tsv
if ($functionDefContainerExists -ne "true") {
    az storage container create `
      --account-name $storageAccount `
      --name $functionDefinitionsContainer `
      --auth-mode login | Out-Null
}

Write-Step "Uploading function definition blob '$functionDefinitionBlobName'."
Upload-BlobFromFile `
  -StorageAccount $storageAccount `
  -Container $functionDefinitionsContainer `
  -BlobName $functionDefinitionBlobName `
  -FilePath $functionDefinitionAssetPath

if ([bool]$config.deployment.deploy_function_resources) {
    Write-Step "Ensuring function app '$functionAppName'."
    $funcExistsCount = az functionapp list --resource-group $resourceGroup --query "[?name=='$functionAppName'] | length(@)" -o tsv
    if ($funcExistsCount -eq "0") {
        if ($config.function_app.plan_sku -eq "FlexConsumption") {
            az functionapp create `
              --resource-group $resourceGroup `
              --name $functionAppName `
              --storage-account $storageAccount `
              --flexconsumption-location $location `
              --runtime $config.function_app.runtime `
              --runtime-version $config.function_app.runtime_version `
              --functions-version 4 | Out-Null
        } else {
            $planName = Select-Name $config.naming.app_service_plan_name "asp-$prefix"
            $planExists = az functionapp plan show --name $planName --resource-group $resourceGroup -o json 2>$null
            if (-not $planExists) {
                az functionapp plan create `
                  --name $planName `
                  --resource-group $resourceGroup `
                  --sku $config.function_app.plan_sku `
                  --is-linux | Out-Null
            }
            az functionapp create `
              --resource-group $resourceGroup `
              --name $functionAppName `
              --storage-account $storageAccount `
              --plan $planName `
              --runtime $config.function_app.runtime `
              --runtime-version $config.function_app.runtime_version `
              --functions-version 4 | Out-Null
        }
    }

    Write-Step "Ensuring system-assigned managed identity on function app."
    az functionapp identity assign --name $functionAppName --resource-group $resourceGroup --identities [system] | Out-Null

    Write-Step "Resolving Application Insights settings."
    $appInsightsConnString = az functionapp config appsettings list `
      --resource-group $resourceGroup `
      --name $functionAppName `
      --query "[?name=='APPLICATIONINSIGHTS_CONNECTION_STRING'].value | [0]" -o tsv
    $appInsightsInstrumentationKey = az functionapp config appsettings list `
      --resource-group $resourceGroup `
      --name $functionAppName `
      --query "[?name=='APPINSIGHTS_INSTRUMENTATIONKEY'].value | [0]" -o tsv
    if ([string]::IsNullOrWhiteSpace($appInsightsConnString)) {
        $existingInsightsName = az resource list `
          --resource-group $resourceGroup `
          --resource-type "microsoft.insights/components" `
          --query "[0].name" -o tsv
        $appInsightsName = $existingInsightsName
        if ([string]::IsNullOrWhiteSpace($appInsightsName)) {
            $appInsightsName = $defaultAppInsightsName
            az monitor app-insights component create `
              --app $appInsightsName `
              --resource-group $resourceGroup `
              --location $location `
              --application-type web `
              --kind web | Out-Null
        }
        $appInsightsConnString = az monitor app-insights component show `
          --resource-group $resourceGroup `
          --app $appInsightsName `
          --query connectionString -o tsv
        $appInsightsInstrumentationKey = az monitor app-insights component show `
          --resource-group $resourceGroup `
          --app $appInsightsName `
          --query instrumentationKey -o tsv
    }

    $openAIEndpoint = "https://$openAIAccount.openai.azure.com/"
    $appSettings = @(
        "APP_CONFIG_PATH=$($config.app_settings.app_config_path)",
        "STORAGE_ACCOUNT_NAME=$storageAccount",
        "OUTPUT_PUSH_TO_SINK=$($config.app_settings.output_push_to_sink.ToString().ToLower())",
        "AZURE_OPENAI_ENDPOINT=$openAIEndpoint",
        "AZURE_OPENAI_DEPLOYMENT=$($config.openai.deployment_name)",
        "SOURCE_CONTAINER=$sourceContainer",
        "OUR_COMPANY_PROFILE_BLOB_NAME=$ourCompanyProfileBlobName",
        "APPLICATIONINSIGHTS_CONNECTION_STRING=$appInsightsConnString",
        "APPINSIGHTS_INSTRUMENTATIONKEY=$appInsightsInstrumentationKey"
    )
    if (-not [string]::IsNullOrWhiteSpace($config.app_settings.openai_api_version)) {
        $appSettings += "AZURE_OPENAI_API_VERSION=$($config.app_settings.openai_api_version)"
    }
    Write-Step "Applying function app settings."
    az functionapp config appsettings set `
      --resource-group $resourceGroup `
      --name $functionAppName `
      --settings $appSettings | Out-Null

}

if ([bool]$config.deployment.deploy_openai_resources) {
    Write-Step "Ensuring Azure OpenAI account '$openAIAccount'."
    $openAIExistsCount = az cognitiveservices account list --resource-group $resourceGroup --query "[?name=='$openAIAccount'] | length(@)" -o tsv
    if ($openAIExistsCount -eq "0") {
        az cognitiveservices account create `
          --name $openAIAccount `
          --resource-group $resourceGroup `
          --kind OpenAI `
          --sku $config.openai.sku_name `
          --location $location `
          --custom-domain $openAIAccount | Out-Null
    }

    Write-Step "Ensuring Azure OpenAI model deployment '$($config.openai.deployment_name)'."
    $deploymentExists = az cognitiveservices account deployment list `
      --name $openAIAccount `
      --resource-group $resourceGroup `
      --query "[?name=='$($config.openai.deployment_name)'] | length(@)" -o tsv
    if ($deploymentExists -eq "0") {
        az cognitiveservices account deployment create `
          --name $openAIAccount `
          --resource-group $resourceGroup `
          --deployment-name $config.openai.deployment_name `
          --model-format OpenAI `
          --model-name $config.openai.model_name `
          --model-version $config.openai.model_version `
          --sku-name $config.openai.deployment_sku_name `
          --sku-capacity $config.openai.capacity | Out-Null
    }

    $openAIScope = az cognitiveservices account show --resource-group $resourceGroup --name $openAIAccount --query id -o tsv
    Write-Step "Ensuring script executor OpenAI roles."
    Ensure-RoleAssignment -PrincipalId $executorObjectId -PrincipalType User -Scope $openAIScope -Role "Cognitive Services OpenAI Contributor"
    Ensure-RoleAssignment -PrincipalId $executorObjectId -PrincipalType User -Scope $openAIScope -Role "Cognitive Services OpenAI User"
}

if ([bool]$config.deployment.deploy_function_resources -and [bool]$config.deployment.deploy_openai_resources) {
    Write-Step "Ensuring RBAC assignments for managed identity."
    $principalId = az functionapp identity show --resource-group $resourceGroup --name $functionAppName --query principalId -o tsv
    if ([string]::IsNullOrWhiteSpace($principalId)) {
        throw "Could not resolve function app managed identity principal id."
    }

    $openAIScope = az cognitiveservices account show --resource-group $resourceGroup --name $openAIAccount --query id -o tsv

    Ensure-RoleAssignment -PrincipalId $principalId -Scope $storageScope -Role "Storage Blob Data Contributor"
    Ensure-RoleAssignment -PrincipalId $principalId -Scope $openAIScope -Role "Cognitive Services OpenAI User"
}

Write-Step "Deployment complete."
Write-Output ""
Write-Output "Resource group: $resourceGroup"
Write-Output "Storage account: $storageAccount"
Write-Output "Function app: $functionAppName"
Write-Output "OpenAI account: $openAIAccount"
