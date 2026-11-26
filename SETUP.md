# Setup Steps and Notes

## Ingestion

The source documents are loaded into the `sources` vector index (S3 Vectors) by a local
Python command-line tool. The plan and its results are in
[Project/Plans/02.Ingestion.md](Project/Plans/02.Ingestion.md); the infrastructure it writes
to is in [Infrastructure/README.md](Infrastructure/README.md).

### Setup

1. Install [uv](https://docs.astral.sh/uv/), then `uv sync` (Python 3.14 and the pinned
   dependencies from `uv.lock`).
2. Copy `.env.example` to `.env` and fill it in. Ingestion needs `AWS_PROFILE`,
   `MODEL_EMBEDDING` and `EMBEDDING_DIMENSION`. The model is Amazon Titan Text V2
   (`amazon.titan-embed-text-v2:0`, 1024-d), called through AWS Bedrock with your AWS
   credentials, so no API key is needed. `INGEST_OPENROUTER_API_KEY` is only used to compare
   OpenRouter models (`embed --model <id>`); if it's left as its placeholder, it's read from
   SSM (`/climate-chat/ingest/openrouter-api-key`).
3. Sign in to AWS (`aws sso login`) before the `embed` and `load` stages or `evaluate --env`.
4. Download the PDFs into `sources/docs/` using the file names in
   [sources/index.md](sources/index.md). The folder is gitignored.

Tests and lint: `uv run pytest` and `uv run ruff check .` (no network or PDFs needed).

### Stages

Run each stage with `uv run python -m climate_chat.ingest <stage>`. Each stage reads and
writes the gitignored `build/` folder, so any of them can be re-run on its own. With no
`--source`, a stage processes every source in `sources/manifest.toml` marked
`ingest = true`; `--source 05` (repeatable) limits it.

| Stage | Does | Time for the whole corpus |
|---|---|---|
| `extract` | PDF to cleaned text per page (`build/text/`) | ~3 min |
| `chunk` | Text to ~500-token chunks with page ranges (`build/chunks/`) | seconds |
| `embed` | Chunks to vectors with `MODEL_EMBEDDING`, cached by content hash (`build/embeddings/`) | ~2.5 min, ~$0.10 (Titan, limited by the account's 300,000 tokens a minute) |
| `load --env dev` | Vectors and metadata into that environment's `sources` index | ~20 s |
| `evaluate --env dev` | The 20 test myths in `eval/retrieval_myths.toml` against the live index, compared with an in-memory search | ~20 s |

- `load --dry-run` shows the chunks, new keys and keys to delete for each source, and
  writes nothing.
- Loads are idempotent: each source's chunks are written, then its old keys that weren't
  rewritten are deleted. A load without `--source` also removes sources that are no longer
  ingested.
- `embed` only pays for chunks whose text changed. `evaluate --in-memory` searches the
  cached vectors without touching AWS.
- `evaluate --env` exits non-zero if the live index and the in-memory search find
  different numbers of myths, which points to a loading problem.

### Re-ingesting (runbook)

Re-ingest when a source is added or replaced, when a web-page snapshot is re-captured, or
when the extraction or chunking code changes.

1. **Re-capture the web-page snapshots** if their data matters: #07, #08, #09, #25, #26,
   #27, #28, #29, #32, #33 and #37 (and #10 and #35, though they aren't ingested). Print each page to PDF from a
   browser under its existing file name in `sources/docs/`, then update `captured` in
   `sources/manifest.toml` and the capture date in `sources/index.md`.
2. **For a new source:** save the PDF as `sources/docs/<id>-<name>.pdf`, add a row to
   `sources/index.md` (including its reuse terms) and a `[[source]]` entry to
   `sources/manifest.toml`, then run `uv run pytest`: a test checks that the two lists
   agree. Optionally add a myth it should answer to `eval/retrieval_myths.toml`.
3. **Rebuild the changed sources** (leave out `--source` to rebuild everything):

   ```bash
   uv run python -m climate_chat.ingest extract --source 07 --source 25
   uv run python -m climate_chat.ingest chunk --source 07 --source 25
   uv run python -m climate_chat.ingest embed --source 07 --source 25
   ```

   Check `extract`'s output for warnings (pages that look scanned) and for a source whose
   kept-text share is much lower than usual.
4. **Load and check dev:**

   ```bash
   uv run python -m climate_chat.ingest load --env dev --source 07 --source 25 --dry-run
   uv run python -m climate_chat.ingest load --env dev --source 07 --source 25
   uv run python -m climate_chat.ingest evaluate --env dev
   ```

   The evaluation runs all 20 myths, so it also catches a change that hurts other
   sources' retrieval. Expect at least 18/20 recall@5 (Titan's two known misses are "no
   warming since 1998" and "fuel prices soaring because of climate policies"), matching the
   in-memory search.
5. **Repeat step 4 with `--env prod`.**

**Changing the embedding model** means re-embedding everything and replacing both indexes
if the dimension changes. Compare candidates first with `embed --model <id>` and
`evaluate --in-memory --model <a> --model <b>` (candidates are listed in
`climate_chat/ingest/embed.py`; `amazon.` ids use Bedrock, others OpenRouter), then follow
[Project/Plans/06.Embeddings.md](Project/Plans/06.Embeddings.md)'s rollout: code first,
then the Terraform change, then re-ingest dev and prod straight away.

## Service

The `/api/chat` service turns a climate-sceptic comment into a short, cited reply. It runs
as a Lambda behind CloudFront at `https://climate-chat.<domain>/api/chat`. How it behaves is
in [Project/Design.md](Project/Design.md); the plan and its results are in
[Project/Plans/03.Service.md](Project/Plans/03.Service.md).

### Local setup

1. `uv sync`, then copy `.env.example` to `.env` (see Ingestion above). The service also
   needs `OPENROUTER_API_KEY` (the credit-capped dev key, for the chat models) and
   `LOG_HASH_KEY` (any long random string, e.g. `openssl rand -hex 32`).
   `TURNSTILE_SECRET_KEY` is already Cloudflare's always-pass test secret, so any token
   works locally, and `TURNSTILE_HOSTNAMES=example.com` is the hostname that secret reports.
   In prod, a token must come from `climate-chat.<domain>` with the action `chat`.
2. `aws sso login`. Locally the service uses the dev data stores (the `sources` and
   `response-cache` indexes and the `logs` and `ratelimits` tables) and embeds claims with
   Titan on Bedrock, all with your AWS credentials.

### Running it

```bash
uv run python -m climate_chat.service.local            # http://127.0.0.1:8000/api/chat
curl -s localhost:8000/api/chat \
  -d '{"comment":"Solar is useless at night","turnstile_token":"XXXX.DUMMY.TOKEN.XXXX","platform":"x"}'
```

The body is `{ comment, turnstile_token, platform?, style?, subject?, thread? }` and the
reply is `{ reply, citations, fallacy, cached }`. `platform` is `x`, `youtube` or
`facebook`; `style` is `match` (the default) or `neutral`. `subject` (up to 300 characters:
what the comment is under, e.g. a video title) and `thread` (up to 1,000: the message it
replies to) are optional free text that help the bot understand short comments. They're
treated as untrusted, like the comment. Error codes are listed in Design.md.

To see every step for one comment (the claim, each model call's output and cost, failed
checks, the reply and citations), without touching the cache:

```bash
uv run python scripts/try_chat.py "mine barely works below 5C, waste of money" \
  --subject "YouTube: Our heat pump after one UK winter" --platform youtube [--prompts]
```

### Tests and evaluation

| Command | What it does | Cost |
|---|---|---|
| `uv run pytest` | Unit tests; no network | Free |
| `uv run pytest -m live` | One real Titan call, and the 20 myths in `eval/retrieval_myths.toml` through the service's own search against dev (at least 18 must find a source) | Under $0.001 |
| `uv run python -m climate_chat.service.evaluate [--runs 2]` | The comments in `eval/replies.toml` (some with `subject` or `thread`), end to end against dev, written to `build/reports/replies.md` to read by hand, with any failed checks | About $0.01 per run |

The evaluation writes answer cards into the dev `response-cache`. To test prompt changes
from scratch, empty that index first; cache hits skip the Facts call.

### Deploying

Merging to `main` deploys, through `.github/workflows/service.yml`:

1. `test`: ruff and `pytest` (also on every pull request).
2. `package`, on a Linux arm64 runner: `scripts/build_lambda.sh` builds
   `build/lambda/climate-chat-api.zip` (runtime dependencies only, no `ingest/`), and the
   handler is imported from the unzipped package. On `main` it then runs
   `update-function-code` on `climate-chat-prod-api`. Finally it checks that a POST with
   no Turnstile token gets `403 turnstile_failed` through CloudFront.

Every POST needs an `x-amz-content-sha256` header holding the hex SHA-256 of the body,
because CloudFront's origin access control signs the request with it (see
[Infrastructure/README.md](Infrastructure/README.md)). Model ids and tuned values
(`MAX_TOKENS_*`, `CACHE_MAX_DISTANCE`, `EXCLUDED_LICENCES`) are Lambda environment
variables set by Terraform (`Infrastructure/app/variables.tf`, `service`), so changing
them is an infrastructure change, not a code deploy.

### Smoke test (prod)

Real Turnstile tokens only come from the widget, so the full pipeline in prod is tested
with a direct invoke. The function URL only accepts CloudFront, so only IAM principals
can do this:

```bash
aws lambda invoke --function-name climate-chat-prod-api --cli-binary-format raw-in-base64-out \
  --payload '{"smoke":"Solar is useless because it does not work at night"}' /dev/stdout
```

It returns the same JSON as the API and is logged with `user_hash = "smoke"`.

### Reading the logs

Each request is one item in `climate-chat-<env>-logs`, with `pk = day#YYYY-MM-DD` and
`sk = <time>#<request id>`. An item holds the comment, claim, outcome, cache hit, latency,
and each model call's tokens and cost. A failed model output adds a `failures` list with
the problems found. No IP is stored. To see whether a few users make most of the requests
on a day, count items by `user_hash` (a monthly keyed hash of the IP):

```bash
aws dynamodb query --table-name climate-chat-prod-logs \
  --key-condition-expression "pk = :d" --expression-attribute-values '{":d":{"S":"day#2026-11-24"}}' \
  --query "Items[].user_hash.S" --output text | tr '\t' '\n' | sort | uniq -c | sort -rn | head
```

Errors with stack traces are in CloudWatch Logs, `/aws/lambda/climate-chat-prod-api`.

The easier way is the logs page, `https://climate-chat.<domain>/logs` (or `/logs` on the
local dev server): a table of requests, newest first, 25 to a page. It asks for the admin
key, which it sends as `X-Admin-Key` to `GET /api/logs`. Without the right key the API
answers 404. To set the key:

1. Generate one per environment with `openssl rand -base64 32` and keep it in your password
   manager. The service refuses any key under 32 characters, so the `CHANGE_ME` placeholder
   that bootstrap creates never works.
2. Put them in `Infrastructure/secrets.local.env` as `PROD_ADMIN_KEY` and `DEV_ADMIN_KEY`,
   then run `Infrastructure/scripts/put-secrets.sh`. For local runs, also set `ADMIN_KEY`
   in `.env` (or leave it out and the service reads `/climate-chat/dev/admin-key`).
3. To rotate, set a new value the same way. The Lambda picks it up within 5 minutes.

## UI

The page at `https://climate-chat.<domain>/` is a plain one-shot form: paste a comment, add
context if you have it, and get one cited reply to copy. It's a Solid 2 + Vite + TypeScript
app in `ui/`, styled as little as possible until the full design replaces it. The plan and
its results are in [Project/Plans/04.UI.md](Project/Plans/04.UI.md).

### Setup

1. Node 24 and pnpm 12.14.0 (pinned in `ui/package.json`).
2. `cd ui && pnpm install`. pnpm installs nothing published in the last 5 days, refuses any
   package whose trust level drops, and runs no install scripts (`ui/pnpm-workspace.yaml`).

### Running it locally

In two terminals, from the repo root:

```bash
uv run python -m climate_chat.service.local
```

```bash
pnpm --dir ui dev
```

Open `http://localhost:5173`. Vite forwards `/api/*` to the local service on port 8000,
which uses the dev data stores. `ui/.env.development` holds Cloudflare's always-pass test
site key, which pairs with the test secret and `TURNSTILE_HOSTNAMES=example.com` in `.env`,
so the whole flow works locally. `.claude/launch.json` has both servers for the app's
browser pane.

### Tests

From `ui/`: `pnpm test` (Node's built-in test runner on `src/*.test.ts`: character counts,
the request body and its hash, reading replies and errors, which URLs become links),
`pnpm typecheck` and `pnpm build`. The components themselves are checked in a browser.

### Adding a package

**Every package passes a security audit before it's used.** Before `pnpm add`, check the
package against its project's own repo or docs (use the install command published there),
its publisher, its provenance (`npm view <pkg> dist.attestations`), any install scripts,
and how many packages it pulls in. Record the result as a bullet under "04. UI" in
[Project/Plan.md](Project/Plan.md). CI runs `pnpm audit` on every build and fails on any
known vulnerability.

### Deploying

Merging to `main` with changes under `ui/` runs `.github/workflows/ui.yml`:
install with the lockfile, `pnpm audit`, type check, test and build (also on every pull
request), then on `main` it refuses to ship the test site key, uploads the hashed assets
(cached for a year), then `index.html` (`no-cache`), removes old files, invalidates
`index.html` in CloudFront and checks that the live page serves the new build. The real
Turnstile site key comes from the `TURNSTILE_SITE_KEY` repository variable; the secret is
in SSM (`/climate-chat/prod/turnstile-secret-key`).

Turnstile won't issue tokens to an automated browser (it answers error `600010`), so
the prod page is tested by hand in a normal browser.
