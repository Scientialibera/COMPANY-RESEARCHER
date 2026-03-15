# Company Researcher

Two-agent Azure Functions workflow for:
- web research on a target company
- structured sales strategy output via function calling

Everything runs in Azure using Blob Storage + Azure OpenAI + managed identity.

## Architecture

- Trigger: blob indicator file in source container (`_READY`)
- Input: company profile JSON under a company folder
- Agent 1: deep research (`web_search_preview`)
- Agent 2: strategy classification + 5 sales ideas (single function call)
- Output: result JSON in sink container (timestamp suffix enabled)

## Repository Layout

- `function_app.py` - function entry points (blob + manual HTTP queue endpoint)
- `src/company_researcher/` - app modules/workflow
- `config/app_config.toml` - runtime behavior and blob paths
- `deploy/` - CLI deployment scripts + upload assets

## Zero-to-Hero (Cloud)

### 1) Prerequisites

- Azure CLI (`az`)
- Azure Functions Core Tools (`func`)
- Python 3.11+
- Logged in: `az login`

### 2) Configure deployment

Edit `deploy/deploy.config.toml`:
- set a unique `naming.prefix` (this controls resource names)
- set `azure.location`
- optional: set `azure.subscription_id` (or leave empty to use current `az` subscription)
- optional: set explicit names under `[naming]` (or leave empty for prefix-based generated names)

Default generated names (if left empty):
- resource group: `rg-<prefix>`
- storage account: `st<prefix>` (sanitized to Azure rules)
- function app: `func-<prefix>`
- openai account: `aoai-<prefix>`

If Azure OpenAI soft-delete blocks recreation, change only `naming.prefix` and rerun.

### 3) Put your prompts and company profile assets in repo

These files are uploaded by `deploy/deploy-infra.ps1` on every run:

- `deploy/assets/shared/our_company_profile.txt` -> blob `additional-company-info/shared/our_company_profile.txt`
- `deploy/assets/prompts/research/system_prompt.txt` -> blob `prompts/research/system_prompt.txt`
- `deploy/assets/prompts/strategy/system_prompt.txt` -> blob `prompts/strategy/system_prompt.txt`
- `deploy/assets/function_definitions/sales/sales_strategy_function.json` -> blob `function-definitions/sales/sales_strategy_function.json`

### 4) Deploy infra + security + settings

```powershell
pwsh deploy/deploy-infra.ps1 -ConfigPath "deploy/deploy.config.toml"
```

This script idempotently:
- creates RG, storage account, containers, Function App, OpenAI resources
- uploads shared profile + stage prompts + function definition to blob storage
- enables managed identity
- assigns RBAC for both function identity and script executor (no keys required)
- sets Function App settings

### 5) Deploy function code

```powershell
pwsh deploy/deploy-function.ps1 -ConfigPath "deploy/deploy.config.toml"
```

### 6) Upload company input

Default sample file location:
- `deploy/assets/companies/sample_company/company_profile.json`

Upload it with:

```powershell
pwsh deploy/upload-dummy-file.ps1 -ConfigPath "deploy/deploy.config.toml"
```

Or upload your own file:

```powershell
pwsh deploy/upload-dummy-file.ps1 `
  -ConfigPath "deploy/deploy.config.toml" `
  -CompanyFolder "acme" `
  -InputFilePath "C:\path\to\company_profile.json"
```

Then upload indicator blob `_READY` under same folder (or use manual endpoint to queue).

## Where to put data that gets uploaded

- Shared "our company" profile text:
  - `deploy/assets/shared/our_company_profile.txt`
- Research stage prompt:
  - `deploy/assets/prompts/research/system_prompt.txt`
- Strategy stage prompt:
  - `deploy/assets/prompts/strategy/system_prompt.txt`
- Function definition:
  - `deploy/assets/function_definitions/sales/sales_strategy_function.json`
- Company input JSON files:
  - recommended under `deploy/assets/companies/<company>/company_profile.json`

## Security Notes

- No secrets should be committed.
- Keep `config/app_config.toml` with `openai.api_key = ""` for managed identity/token auth.
- `local.settings.json` is placeholder-only and for local dev.
