# Climate Chat: plan

Index of project work. The design is in [Design.md](Design.md); each plan lives in [Plans/](Plans/).

## Progress

| # | Plan | Status | Notes |
|---|---|---|---|
| 01 | [Infrastructure](Plans/01.Infra.md) | Done | Live at climate-chat.<domain>; CI applies prod on merge to main. Runbook: [Infrastructure/README.md](../Infrastructure/README.md) |
| 02 | [Ingestion](Plans/02.Ingestion.md) | Done | Python CLI: manifest → extract → chunk → embed → load → eval. The bake-off chose `text-embedding-3-small` (20/20 myths, 0.7 s p95). 1,811 chunks from 28 sources loaded in dev and prod; both live indexes find all 20 test myths. Runbook: [README.md](../README.md#ingestion) |
| 03 | [Python service (`/api/chat`)](Plans/03.Service.md) | Done | Plain Lambda handler, no framework or new dependencies. Deployed to the prod Lambda by CI on merge to `main` and smoke-tested; not public until plan 04's UI sends real Turnstile tokens. Cache miss ~$0.0010 in 5–8.6 s, hit ~$0.0003 in 2.3–4.4 s. Runbook: [README.md](../README.md#service) |
| 04 | [Solid UI](Plans/04.UI.md) | Done | One-shot page at climate-chat.<domain>, minimal styling, pnpm with every package audited. Works end to end in prod with real Turnstile tokens (hostname and action checked); not launched: licences and the concurrency quota are still open. Runbook: [README.md](../README.md#ui) |
| 05 | [Comment context (`subject`, `thread`)](Plans/05.Context.md) | Done | Two optional free-text fields, treated as an attack vector, used by Classify and ResponseBot only. Live in prod (PR #9). Showed the heat-pump source gap |
| 06 | [Embeddings on Amazon Titan V2](Plans/06.Embeddings.md) | Done | Embeddings on Bedrock in eu-west-2, not OpenRouter. 2,115 chunks including 11 new UK sources; 18/20 myths; cache miss 4.7–7.7 s. Follow-ups: the two weak myths, and #35 needs a printout of its tables |

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
- **Embedding dimension starts at 4096** (Qwen3-Embedding-8B). Changing the model later replaces both indexes and needs a re-ingest. *Superseded in plan 02: the bake-off chose `text-embedding-3-small`, 1536-d.*

### 02. Ingestion

- **A local Python CLI, not CI.** Ingestion is rare and manual. It uses your AWS credentials and the credit-capped `ingest` key. Stages write to a gitignored `build/` folder, so each can re-run on its own.
- **One `src/climate_chat` package** with the embeddings client and vector helpers shared with the service (plan 03), so both embed and query the same way.
- **The embedding bake-off runs in memory** (numpy cosine) before anything is loaded. The 1536-d candidate then needs no extra index. The winner is set in tfvars; if the dimension changes, the indexes are replaced while they're still empty.
- **Winner rule:** higher recall@5 on 20 myths, with ties going to the cheaper, smaller `text-embedding-3-small`. Target recall@5 ≥ 0.8; if it's missed, tune chunking before switching models.
- **No AGPL PDF tools** (PyMuPDF) in a public repo.
- **Chunks of about 500 tokens with 80 overlap**, with page ranges. Headers, footers and reference sections are dropped. Ids are `<source_id>-<chunk_no>`, e.g. `05-0042`.
- **Re-loads are idempotent without a state file:** list the keys for a source, write the new chunks, then delete the keys that weren't rewritten.
- **`sources/manifest.toml` is the machine-readable source list.** A test keeps it in step with `sources/index.md`. TOML rather than YAML: PyYAML failed dependency vetting (its upstream README documents no PyPI install), and the standard library's `tomllib` needs no dependency.
- **pdfplumber is the PDF extractor**, keeping upright characters only. pypdf turned #22 IRENA's numbers into about 20,000 glyph names, even with its `fonts` extra.
- **#10 (NASA sea level) isn't ingested** until a better data source replaces it.
- **Every source's reuse terms are a `licence` value** (`open`, `cc-by`, `non-commercial`, `gov`, `restricted`, `unverified`), taken from the PDF's own notice or the publisher's page, never guessed. All are ingested; which ones the service may quote at launch is one open decision, enforced with a query filter. It covers the non-commercial sources (#08, #21–#23), the short-extract-only ones (#01, #05, #12) and those with no terms found (#02, #03, #06, #16). CC BY-NC counts as `non-commercial`, so one filter value covers it.
- **Query latency is part of the embedding bake-off.** Qwen3 measured 0.6–30 s per query on OpenRouter (`text-embedding-3-small`: 0.3–0.5 s), and the service embeds every claim inside its 4–6 s budget. A model with p95 over 2 s is ruled out before recall is compared.
- **PDF text is read column by column.** pdfplumber reads straight across a page, which interleaves two-column journals. Extraction finds the gutter itself, splitting only where at least one side is prose so tables stay whole, and uses font-relative word gaps so tightly set journals don't glue words together.
- **Chunks that are mostly numbers are skipped** (under 20% words): unlabelled table grids and scrambled chart text can't answer a claim and would only add noise to retrieval. This removes most of #23's statistics tables.
- **The embedding model is `openai/text-embedding-3-small`.** It found all 20 myths' sources against Qwen3's 19, and Qwen3's 12 s p95 query latency on OpenRouter would break the reply budget. Chunks are embedded with their source title as a first line.
- **`Infrastructure/` is excluded from ruff**, so Python formatting never touches the deployed Lambda placeholder or triggers an infra CI run.

### 03. Service

- **Design.md is the source of truth for how the service behaves.** Plans describe how it gets built, tested and deployed, and link to Design.md instead of restating it.
- **Plan 03 ends deployed but not public.** Real Turnstile tokens only come from the widget, so the first public end-to-end test is in plan 04. The prod pipeline is tested with an IAM-only direct-invoke smoke event.
- **A plain Lambda handler, no web framework.** One route doesn't justify FastAPI's four extra packages and slower cold starts. A standard-library `http.server` runner serves the same handler locally.
- **Keep v1 as simple as possible:** no `GET /api/sources`, only the `match` and `neutral` styles, cache lookup then search one after the other.
- **Requests are grouped by a monthly keyed hash of the IP, never the IP itself**, to see whether a few users generate most of the traffic. It needs a new `log-hash-key` SSM secret.
- **`max_tokens` and the cache distance are tuned by testing**, not fixed in advance. Haiku's hidden reasoning counts against `max_tokens`.
- **No `temperature`, reasoning off, schemas enforced.** Phase 0 found neither Haiku 5.5 nor the fallback supports `temperature`. `reasoning: {enabled: false}` stops Haiku's hidden tokens eating the `max_tokens` cap. `require_parameters: true` keeps calls on providers that enforce the JSON schema.
- **The cache starts strict, at a cosine distance of 0.15.** Even after normalising, different claims (methane vs CO2 "natural rise") can sit closer than rewordings of one claim. A wrong card is worse than a miss, so fewer cache hits are accepted.
- **Ingestion-only packages move to an `ingest` dependency group** (still installed by default), so the Lambda zip leaves out `pdfplumber` and `tiktoken`.
- **Comments OpenRouter refuses get a polite fixed reply, not an error.** OpenRouter blocks prompt-injection patterns itself (403). Retrying can't help, so the API returns 200 with "Sorry, I can't reply to that comment." and logs `blocked`.
- **Every output check is code, retried once with feedback.** Citations, numbers, the platform length and a short `fallacy` label are all checked in code. A failure is retried once, with the failed output and the problems found sent back; a second failure is a 502, and the failures are logged.
- **Settings come from the environment alone when there's no repo around the code.** The Lambda zip has no `pyproject.toml`; looking for `.env` through it would have failed every cold start.

### 04. UI

- **A one-shot page for now:** one form in, one reply card out. A chat-style thread would look conversational while each reply has no memory of the last.
- **The form's platform defaults to YouTube** (500-character replies). The API's own default stays at 280 for requests that leave `platform` out.
- **Minimal styling.** The goal is a working end-to-end system; a complete design comes later and replaces the markup and CSS.
- **Plan 04 ends working, not launched.** The real Turnstile widget, the deployed UI and a proven prod round trip. Choosing licences and raising the Lambda concurrency quota come before any publicity.
- **Solid 2 + Vite + TypeScript in `ui/`** (approach A), the stack Design.md chose, so the later design goes straight into it.
- **The service checks the Turnstile token's `hostname` and `action`, not just `success`** (Cloudflare's checklist for an existing widget). An allowlist (`TURNSTILE_HOSTNAMES`) stops tokens issued on other hosts, such as `localhost`, from working; the action `chat` ties tokens to this form; tokens over 2,048 characters are refused without calling Cloudflare. The Terraform setting merges before the code, so prod never runs code that needs a setting it doesn't have yet.
- **A 5-day minimum release age** (`minimumReleaseAge: 7200`). Long enough to catch most hijacked releases, which are usually spotted within a day or two; short enough to take Solid 2's fix releases. Changed from 7 days, which would have held Solid at 2.0.0.
- **pnpm, and every package passes a security audit before it's used.** Direct packages are vetted and recorded here; CI runs `pnpm audit`; install scripts are blocked; a minimum release age keeps out just-published versions.
- **Package audit (Phase 0, 2026-11-24).** Each install command below comes from the upstream project's own README or docs, not from the registry. "Provenance" means npm holds a SLSA v1 attestation linking the package to its source repo's build.
  - **pnpm 12.14.0** (the local version; latest is 12.23.0). Published by the pnpm maintainers (`zkochan`, `pnpmuser` bot) from `github.com/pnpm/pnpm`, with provenance. `npm install -g pnpm@<version>` is one of pnpm.io's documented install methods. The npm package runs `install.js` before and after installing, to link its native binary from the per-platform `@pnpm/exe.*` packages. That's expected for pnpm 12, which is a native executable. **Passes.**
  - **solid-js 2.x and @solidjs/web 2.x.** Published by Ryan Carniato (Solid's author) and `davedbase` from `github.com/solidjs/solid`, with provenance; no install scripts. Solid's README installs both for a Vite app; `@solidjs/web` is the browser renderer (`render`, the JSX types). **Pass.** Solid 2.0.0 came out on 2026-11-17; 2.0.3 (2026-11-19) and every package Solid pulls in are over 5 days old.
  - **@solidjs/vite-plugin 3.x**, not `vite-plugin-solid`. The plugin's README says `vite-plugin-solid` "has moved to `@solidjs/vite-plugin`"; `vite-plugin-solid` 2.11.17 only supports Solid 1 (`solid-js ^1.7.2`). Same publishers and provenance, from `github.com/solidjs/solid-vite-plugin`; needs Vite 8 or 9 and Node 22.12+. **Passes.** 3.0.1 (2026-11-17).
  - **vite 8.3.8** (2026-11-11). Published by Evan You and the `vitebot` account from `github.com/vitejs/vite`, with provenance; no install scripts. Vite's guide documents `pnpm create vite` / `pnpm add -D vite`. It pulls in `rolldown` and `lightningcss`, which ship native binaries as per-platform packages. **Passes.**
  - **typescript 7.0.2** (2026-07-08). Published by Microsoft's accounts from `github.com/microsoft/TypeScript`; native (Go) binaries as per-platform packages; no install scripts. **No provenance attestation**: Microsoft doesn't publish one, so the check rests on the publisher accounts and the upstream docs (`npm install -D typescript`). **Passes.**
  - **The Solid packages' "agent skills" stay unapproved.** pnpm 12 lets packages offer `SKILL.md` files for AI coding agents; `solid-js` and `@solidjs/web` ask to. Unapproved means nothing is installed or granted, and pnpm keeps them listed as awaiting approval.
  - **Only direct packages are vetted by hand.** The ones they pull in are covered by `pnpm audit`, the 5-day release age, blocked install scripts and `trustPolicy: no-downgrade`.

### 05. Comment context

- **Context is free text from the user, not fetched from URLs.** Fetching would need an outbound call, a YouTube key and the handling of long stranger-written descriptions.
- **Two fields: `subject`** (what the comment is under) **and `thread`** (the message it replies to). Both are an attack vector, handled like the comment.
- **Only Classify and ResponseBot see the context.** Facts, the search and the cache work from the restated claim, so cards stay neutral and one card still serves every video.
- **Replies may quote numbers from the comment, subject and thread.** The number check exists to catch invented statistics, and quoted ones aren't invented. The prompt allows them only as references, never as facts.

### 06. Embeddings

- **Embeddings move to Amazon Titan Text V2 on Bedrock (`eu-west-2`).** The OpenRouter account's zero-data-retention setting left `text-embedding-3-small` with one provider, Azure, and its outage failed every claim. Titan runs inside the AWS account, with the Lambda's IAM role and no API key.
- **18 of 20 myths is accepted.** The live retrieval test needs at least 18. The two misses ("no warming since 1998", "fuel prices soaring because of climate policies") are a separate follow-up.
- **The indexes are replaced in place** (approach A). The code merges first, then one Terraform merge, then prod is re-ingested straight away. A few minutes without claims is acceptable before launch.
- **12 UK sources (#30–#41) joined the corpus in the same run**, all under the Open Government Licence. #35 (Boiler Upgrade Scheme statistics) isn't ingested: the release is a spreadsheet, and its printout was charts only; #36 covers the same numbers.
- **The model id picks the provider:** `amazon.` ids use Bedrock, everything else OpenRouter. No new setting.
