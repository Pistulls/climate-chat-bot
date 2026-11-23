# Dev: data stores only. The service and UI run locally against them.
# Personal values (none needed for dev) would go in dev.local.tfvars.
env            = "dev"
create_hosting = false

# Qwen3-Embedding-8B is 4096-d; openai/text-embedding-3-small is 1536-d. Provisional, see Design.md.
embedding_dimension = 4096

models = {
  classify  = "anthropic/claude-haiku-5.5"
  facts     = "anthropic/claude-haiku-5.5"
  reply     = "anthropic/claude-haiku-5.5"
  fallback  = "openai/gpt-6-luna"
  embedding = "qwen/qwen3-embedding-8b"
}
