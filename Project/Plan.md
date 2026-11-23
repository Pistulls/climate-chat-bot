# Climate Chat: plan

Index of project work. The design is in [Design.md](Design.md); each plan lives in [Plans/](Plans/).

## Progress

| # | Plan | Status | Notes |
|---|---|---|---|
| 01 | [Infrastructure](Plans/01.Infra.md) | Planned | Terraform for AWS: hosted zone, cert, data stores, Lambda, CloudFront, SSM, CI role |
| 02 | Ingestion (sources → `sources` index) | Not started | |
| 03 | Python service (`/api/chat`) | Not started | |
| 04 | Solid UI | Not started | |

Status values: Not started, Planned, In progress, Done.

## Decisions

### 01. Infrastructure

- **Public repo: no personal or account details in committed files.** The account ID, state bucket, domain, AWS profile and OIDC subject prefix are supplied through gitignored `*.local.hcl` / `*.local.tfvars` files locally and GitHub Actions variables in CI. Docs use placeholders (`<account_id>`, `<state-bucket>`, `<domain>`, `<owner>`).
- **Same AWS account and region as the website** (`<account_id>`, `eu-west-2`), and the same state bucket (`<state-bucket>`) under its own `climate-chat/` key prefix. This keeps the state separate without a second bootstrap bucket.
- **Two Terraform stacks, mirroring the website.** `Infrastructure/bootstrap/` holds the long-lived pieces (zone, cert, CI role, SSM parameters, budget) and is applied locally as admin. `Infrastructure/app/` holds everything else and is applied by CI on merge to `main`.
- **Own CloudFront distribution, not the website's shared external-subdomain hosting.** The shared distribution is static-only, with no `/api/*` origin and no SPA fallback.
- **Own ACM certificate** for `climate-chat.<domain>`, validated in the project's own zone, rather than reusing the website's wildcard. It's free and keeps the projects independent.
- **NS delegation values are hard-coded in the website repo.** The zone has `prevent_destroy`, so they don't change, and the website's CI role can't read this repo's state.
- **Reuse the existing GitHub OIDC provider** through a data source. A new `github-deploy-climate-chat` role trusts only this repo's `main`, matched by immutable repo IDs.
- **Two envs, `dev` and `prod`, with the env in resource names** (`climate-chat-<env>-…`). Dev has only data stores, so local development doesn't write into the prod cache or logs. Design.md's store names gain the env segment.
- **The SPA fallback uses a CloudFront Function, not custom error responses.** Custom error responses would turn the API's 403/4xx replies into `index.html`.
- **The origin request policy for `/api/*` forwards `CloudFront-Viewer-Address` and drops `Host`.** The rate limiter needs the real client IP, and the function URL rejects a foreign Host.
- **Terraform owns configuration, not code or content.** The Lambda and UI start with placeholders, and `ignore_changes` hands code and content to their own deploy workflows.
- **A $5/month AWS Budget alarm** on the `Project = climate-chat` tag. It's free and backs up the OpenRouter credit caps.
- **14-day log retention, PITR off, and deletion protection on prod tables.** The data can be rebuilt, so backups aren't worth the cost.
