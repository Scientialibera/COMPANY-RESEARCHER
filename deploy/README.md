# Deploy Folder

CLI-only deployment.

## Scripts

1. `deploy-infra.ps1`
   - deploys infra (idempotent)
   - uploads shared profile + prompts + function definition from `deploy/assets/`
   - sets app settings + managed identity + RBAC (executor + function identity)
   - registers Event Grid provider, syncs function triggers, and creates Event Grid subscription with Azure Function destination type

2. `deploy-function.ps1`
   - publishes Azure Functions code

3. `upload-dummy-file.ps1`
   - uploads one company profile JSON into the source container

## Assets uploaded by infra script

- `assets/shared/our_company_profile.txt`
- `assets/prompts/research/system_prompt.txt`
- `assets/prompts/strategy/system_prompt.txt`
- `assets/function_definitions/sales/sales_strategy_function.json`

## Company JSON for upload script

Default input:
- `assets/companies/sample_company/company_profile.json`

Custom input:
- pass `-InputFilePath <path-to-json>`
