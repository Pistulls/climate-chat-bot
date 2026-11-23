# Dev: data stores only. The service and UI run locally against them.
# Personal values (none needed for dev) would go in dev.local.tfvars.
env            = "dev"
create_hosting = false

# openai/text-embedding-3-small is 1536-d. Chosen by the plan 02 bake-off, see Design.md.
embedding_dimension = 1536

models = {
  classify  = "anthropic/claude-haiku-5.5"
  facts     = "anthropic/claude-haiku-5.5"
  reply     = "anthropic/claude-haiku-5.5"
  fallback  = "openai/gpt-6-luna"
  embedding = "openai/text-embedding-3-small"
}
