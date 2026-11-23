# Infrastructure

Terraform for Climate Chat on AWS. The plan and its reasoning are in [Project/Plans/01.Infra.md](../Project/Plans/01.Infra.md).

| Stack | What | Applied by | State key |
|---|---|---|---|
| `bootstrap/` | Hosted zone, ACM cert, CI deploy role, SSM parameters, budget | You, locally as admin | `climate-chat/bootstrap/terraform.tfstate` |
| `app/` (`dev`) | Vector bucket + indexes, DynamoDB tables | You, locally | `climate-chat/dev/terraform.tfstate` |
| `app/` (`prod`) | The above, plus Lambda, UI bucket, CloudFront, DNS records (`modules/hosting`) | CI on merge to `main` | `climate-chat/prod/terraform.tfstate` |

## Public repo: personal values stay local

The account ID, state bucket, domain, OIDC subject prefix and budget email are never committed. Copy each example file to its gitignored `*.local.*` name:

| Example (committed) | Local copy (gitignored) |
|---|---|
| `bootstrap/backend.example.hcl` | `bootstrap/backend.local.hcl` |
| `bootstrap/example.tfvars` | `bootstrap/bootstrap.local.tfvars` |
| `app/backend.example.hcl` | `app/backend.dev.local.hcl`, `app/backend.prod.local.hcl` |
| `app/example.tfvars` | `app/prod.local.tfvars` |

CI gets the same values from repo **secrets** `AWS_DEPLOY_ROLE_ARN` and `TF_STATE_BUCKET`, and repo **variable** `DOMAIN_NAME`.

## First-time setup

Never run `apply` without reading the plan first.

```bash
export AWS_PROFILE=<admin-profile>   # aws sso login --profile <admin-profile>
aws sts get-caller-identity
```

### 1. Bootstrap the zone, then delegate it

```bash
cd Infrastructure/bootstrap
terraform init -backend-config=backend.local.hcl
terraform plan -var-file=bootstrap.local.tfvars                      # expect 12 to add
terraform apply -var-file=bootstrap.local.tfvars -target=aws_route53_zone.main
terraform output -json name_servers
```

In the website repo, add an `NS` record for `climate-chat.<domain>` with those four values (TTL 3600) and merge it. Then check the delegation:

```bash
dig NS climate-chat.<domain> +short
```

### 2. Apply the rest of bootstrap

Certificate validation waits until the delegation resolves.

```bash
terraform apply -var-file=bootstrap.local.tfvars
```

Then the manual steps:

- Set the four SSM values: `aws ssm put-parameter --name <name> --type SecureString --value "<key>" --overwrite`. The names are in `terraform output ssm_parameter_names`.
- Activate the `Project` cost allocation tag in Billing so the budget can filter on it.
- Store the CI values:

  ```bash
  gh secret set AWS_DEPLOY_ROLE_ARN --body "$(terraform output -raw github_deploy_role_arn)"
  gh secret set TF_STATE_BUCKET --body "<state-bucket>"
  gh variable set DOMAIN_NAME --body "<domain>"
  ```

### 3. Dev data stores

```bash
cd ../app
terraform init -reconfigure -backend-config=backend.dev.local.hcl
terraform plan -var-file=envs/dev.tfvars                             # expect 5 to add
terraform apply -var-file=envs/dev.tfvars
```

### 4. Prod, first time locally

The first apply runs locally, so any permission gaps in the CI role don't block it. After that, CI applies on merge.

```bash
terraform init -reconfigure -backend-config=backend.prod.local.hcl
terraform plan -var-file=envs/prod.tfvars -var-file=prod.local.tfvars
terraform apply -var-file=envs/prod.tfvars -var-file=prod.local.tfvars
```

## Checks after prod is up

```bash
curl -sI https://climate-chat.<domain>/                   # 200, placeholder index.html
curl -sI https://climate-chat.<domain>/some/route         # 200, SPA fallback
body='{}'; curl -s -X POST https://climate-chat.<domain>/api/chat \
  -H 'content-type: application/json' \
  -H "x-amz-content-sha256: $(printf %s "$body" | shasum -a 256 | cut -d' ' -f1)" \
  -d "$body"                                              # 503 {"error":"not deployed"} from Lambda
```

- Calling the function URL directly should return 403.
- The placeholder logs `cloudfront_viewer_address` to `/aws/lambda/climate-chat-prod-api`. It should show your IP.

## Notes

- **Reserved concurrency** is off (`concurrency = -1`). The account's Lambda concurrency quota is 10, and AWS keeps 10 unreserved. Request an increase (Service Quotas, `L-B99A9384`), then set `lambda.concurrency` in `envs/prod.tfvars`.
- **Changing the embedding model's dimension** replaces both indexes. Update `embedding_dimension` in both tfvars files and re-run ingestion.
- **Lambda code and UI content** belong to their own deploys. Terraform ignores changes to both after the first apply.
