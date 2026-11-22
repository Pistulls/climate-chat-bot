# Climate Bot: design decisions

![ClimateBotDesign2.png](ClimateBotDesign2.png)

Working record of decisions made while fleshing out the design. Diagram: StateFlow FigJam board, "Climate Bot v2: Data Stores".

## Principles

- **Pay per use, no minimum charges.** Every service must cost (close to) nothing when idle.
- **Own repo, own infra.** This project has its own Terraform state and its own Route 53 hosted zone for `climate-chat.<domain>`. The website repo only adds the NS delegation record.

## Data stores

| Diagram box | Service | Name |
|---|---|---|
| Response Cache | S3 Vectors index; reply text in vector metadata | bucket `climate-chat-vectors`, index `response-cache` |
| Fact Sources | S3 Vectors index; chunk text, source number and citation URL in metadata | bucket `climate-chat-vectors`, index `sources` |
| Log Store | DynamoDB on-demand, TTL on log items | table `climate-chat-logs` |
| Rate limits (not in diagram yet) | DynamoDB on-demand, one counter item per IP per time window, TTL expiry | table `climate-chat-ratelimits` |

- Compute: Lambda **outside a VPC** (no NAT Gateway). Static UI on S3 + CloudFront.
- Avoided because of minimum charges: OpenSearch Serverless, always-on RDS/Aurora, ElastiCache, NAT Gateway.
- Expected idle cost: about $1–2/month, mostly the Route 53 hosted zone.

## Front end and API

**No separate backend for the front end (no BFF).** The UI talks directly to the Python service. A BFF would only pay off with user logins, several backends to combine, server-side rendering for SEO, or secrets to keep out of the browser, and none of those apply here.

```
climate-chat.<domain>  →  CloudFront
                           ├─ /*      → S3 (static Solid single-page app)
                           └─ /api/*  → Lambda function URL (Python service)
```

- **UI:** plain **Solid 2 + Vite** single-page app (`solid-js` 2.0.3 and `vite-plugin-solid` 2.11.17 were current on npm on 2026-11-22). SolidStart isn't used, because its value is server rendering and server functions.
- **One domain:** CloudFront sends `/api/*` to the Lambda function URL, so no CORS setup is needed. The function URL is locked to CloudFront with Origin Access Control (OAC), so direct calls are refused.
- **API routes:**
  - `POST /api/chat`: takes `{ comment, turnstile_token }` and returns `{ reply, citations, fallacy, cached }`
  - `GET /api/sources` (optional): returns the source list with links for the UI
- **No streaming:** replies are short (~300 tokens), and Lambda's Python runtime doesn't support response streaming natively. The UI shows a typing indicator while it waits.

### Abuse protection for the anonymous endpoint

Anyone can call `/api/chat`, and every cache miss costs money. Protection is layered, and almost all of it is free:

1. **Cloudflare Turnstile check** (planned, free): see below.
2. **Per-IP rate limit** in the Python service, using counters in the `climate-chat-ratelimits` table (e.g. 10 requests/minute, 100/day). Each counter item expires via TTL.
3. **Comment length cap** (~1,000 characters), checked before any LLM call.
4. **Lambda reserved concurrency** to cap how many requests run at once.
5. **OpenRouter key credit cap** as the hard limit on spending.

AWS WAF with CAPTCHA was considered and not chosen: it costs at least $5/month and Turnstile does the same job for free.

### Cloudflare Turnstile

Turnstile is Cloudflare's free bot check. It works on any site, so the domain doesn't need to be on Cloudflare DNS.

1. The Solid app renders the Turnstile widget in **managed mode**, so most people never see a challenge. The widget uses the public **site key**, which is baked into the UI build.
2. Each `POST /api/chat` sends the widget's token with the comment: `{ comment, turnstile_token }`.
3. The Python service verifies the token with Cloudflare's `siteverify` endpoint, using the private **secret key**, **before** the rate limit, the cache lookup or any LLM call. A missing or failed token returns HTTP 403.
4. Tokens are single-use and expire after 5 minutes, so the UI requests a fresh token for each message.

The secret key is stored like the OpenRouter keys (see Secrets).

## LLM (OpenRouter)

All model calls go through OpenRouter's OpenAI-compatible API (`https://openrouter.ai/api/v1`), using the OpenAI Python SDK.

### Models

Prices are per million tokens (input / output), from OpenRouter's public model list on 2026-11-22.

| Role | Model | Price | Why |
|---|---|---|---|
| Question Guard | `anthropic/claude-haiku-5.5` | $0.10 / $0.50 | Strong instruction-following and resistance to prompt injection. A guard call is ~400 tokens in, ~50 out, so a cheaper model would save under $0.0001 per call. One model for both roles keeps prompts and testing simple. |
| ResponseBot | `anthropic/claude-haiku-5.5` | $0.10 / $0.50 | Best quality in the low-cost tier. Supports structured outputs. |
| Fallback (both) | `openai/gpt-6-luna` | $0.10 / $0.50 | Same price tier, different vendor, so an Anthropic outage doesn't take the bot down. |
| Embeddings | `qwen/qwen3-embedding-8b` | $0.01 | Strong retrieval quality at half the price of `openai/text-embedding-3-small` ($0.02). |

**Embedding choice is provisional.** Before locking it in, embed the corpus with both Qwen3-Embedding-8B and `openai/text-embedding-3-small` (a few cents each), then test retrieval with ~20 known myths. Keep the winner.

Embeddings cannot use a fallback model. Both indexes must be built and queried with the same model, and changing it means re-embedding everything (cheap at this corpus size).

Model IDs live in config (environment variables), not code, so they can change without a deploy. The fallback goes in OpenRouter's `models` list on each request.

### Expected cost per reply

| Call | Tokens (approx.) | Cost |
|---|---|---|
| Question embedding | 50 | ~$0.0000005 |
| Question Guard | 400 in, 50 out | ~$0.00007 |
| ResponseBot (cache miss only) | 2,500 in (instructions + 5 chunks), 250 out | ~$0.0004 |
| **Total, cache miss** | | **~$0.0005** (about 2,000 replies per $1) |
| **Total, cache hit** | | **~$0.00007** (guard + embedding only) |

One-off ingestion of the 18 sources: roughly 1M tokens of embeddings, about $0.01.

### Cost and abuse controls

- **A credit cap on each OpenRouter key.** Separate keys for `prod`, `dev` and `ingest`. A spent key returns HTTP 402, and the bot replies "can't answer right now".
- Strict `max_tokens` (reply ~300, guard ~60) and low temperature.
- API key stored as an SSM Parameter Store SecureString (free tier), not Secrets Manager.
- Token usage and cost from each response's `usage` field written to `climate-chat-logs`.
- Provider routing set to deny data collection and prefer providers that don't retain data.

### Reply quality

- Fixed reply structure from the Debunking Handbook 2020: **fact → warning → fallacy → fact**.
- Structured output: `{ reply, citations: [source_id], fallacy, cards_category, confidence }`.
- **Citation check in code:** every cited `source_id` must be one of the retrieved chunks, or the reply is rejected.
- The guard tags each comment with a CARDS category (Coan et al. 2021), which is also stored as cache metadata.

## Secrets

The secrets are the **OpenRouter API keys** (`prod`, `dev`, `ingest`) and the **Cloudflare Turnstile secret key**. The Turnstile site key is public and lives in the UI build. The Python service reaches S3 Vectors and DynamoDB through its Lambda IAM role, so no AWS keys are stored anywhere.

### Where they live

**SSM Parameter Store, SecureString, standard tier.** Storage and normal API calls are free, and encryption uses the free AWS-managed `aws/ssm` key.

Secrets Manager was not chosen. It costs $0.40 per secret per month plus API charges, and its main extra, automatic rotation, can't be used with OpenRouter keys.

| Parameter | Used by |
|---|---|
| `/climate-chat/prod/openrouter-api-key` | Python service (Lambda) |
| `/climate-chat/dev/openrouter-api-key` | Shared dev copy. Local development reads the key from a gitignored `.env` |
| `/climate-chat/prod/turnstile-secret-key` | Python service (Lambda) |
| `/climate-chat/ingest/openrouter-api-key` | Ingestion script, using your own AWS credentials (or a GitHub Actions OIDC role if run in CI) |

### Rules

1. **Terraform creates the parameter, never the value.** Values in Terraform end up in plain text in the state file. Each parameter is created with a placeholder and `lifecycle { ignore_changes = [value] }`. The real value is set once, outside Terraform:

   ```bash
   aws ssm put-parameter --name /climate-chat/prod/openrouter-api-key --type SecureString --value "<key>" --overwrite
   ```

2. **No secrets in Lambda environment variables.** They are visible in the console and in Terraform state. The service reads the key with boto3 (`get_parameter`, `WithDecryption=True`) when it starts, and caches it in memory for about 5 minutes.
3. **Least-privilege IAM.** The Lambda role gets `ssm:GetParameter` on the two prod parameters' ARNs only, plus `kms:Decrypt` on the `aws/ssm` key.

### Rotating a key and limiting damage

- **To rotate:** create a new key in OpenRouter, overwrite the parameter, and revoke the old key. The service picks up the new key within the 5-minute cache window, with no deploy.
- **If a key leaks:** each key's OpenRouter credit cap limits the most it can cost. Separate keys mean a leaked dev or ingest key doesn't affect prod.

**Cost: $0.**

## Response cache writes

Generated replies are **written straight into the `response-cache` index**, with no review step. Only replies that pass the citation check are written. `confidence`, `cards_category` and the source IDs are stored as metadata, so weak entries can be found and removed later.
