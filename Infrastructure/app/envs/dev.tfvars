# Dev: data stores only. The service and UI run locally against them.
# Personal values (none needed for dev) would go in dev.local.tfvars.
env            = "dev"
create_hosting = false

# amazon.titan-embed-text-v2:0 on Bedrock, 1024-d (plan 06, see Design.md). Changing the
# dimension replaces both indexes; re-ingest afterwards.
embedding_dimension = 1024

models = {
  classify  = "anthropic/claude-haiku-5.5"
  facts     = "anthropic/claude-haiku-5.5"
  reply     = "anthropic/claude-haiku-5.5"
  fallback  = "openai/gpt-6-luna"
  embedding = "amazon.titan-embed-text-v2:0"
}
