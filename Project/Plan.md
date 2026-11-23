# Climate Chat: plan

Index of project work. The design is in [Design.md](Design.md); each plan lives in [Plans/](Plans/).

## Progress

| # | Plan | Status | Notes |
|---|---|---|---|
| 01 | [Infrastructure](Plans/01.Infra.md) | Done | Live at climate-chat.<domain>; CI applies prod on merge to main. Runbook: [Infrastructure/README.md](../Infrastructure/README.md) |
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
- **Prod-only resources live in a `modules/hosting` module behind `create_hosting`.** This keeps `[0]` indexing out of every resource, and dev stays data stores only.
- **No reserved Lambda concurrency for now.** The account quota is 10 and AWS keeps 10 unreserved. Raise the quota, then set `lambda.concurrency`.
- **Lambda runtime `python3.14` on `arm64`**, and AWS provider pinned to `~> 6.73` for the S3 Vectors resources.
- **The `/api/*` origin request policy is a header allow-list**, not the managed `AllViewerExceptHostHeader`. The managed policy doesn't forward `CloudFront-Viewer-Address`.
- **CI's role ARN and state bucket are Actions secrets, not variables,** so they're masked in public logs. `mask-aws-account-id` covers the account ID in plan output. The domain is an ordinary variable because it's public anyway.
- **The CI role has no `DeleteDistribution`**, as for the website's role. CloudFront ARNs use generated IDs, so CloudFront write access can't be narrowed to this project's distribution.
- **The `/api/*` origin request policy doesn't list `X-Amz-Content-Sha256`.** CloudFront rejects `X-Amz-*` headers in a policy, and OAC reads the viewer's payload hash itself. Found on the first prod apply.
- **Embedding dimension starts at 4096** (Qwen3-Embedding-8B). Changing the model later replaces both indexes and needs a re-ingest.
