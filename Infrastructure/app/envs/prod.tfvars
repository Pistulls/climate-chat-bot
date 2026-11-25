# Prod: everything. domain_name comes from prod.local.tfvars locally, TF_VAR_domain_name in CI.
env            = "prod"
create_hosting = true

# Must match dev so the same ingestion code works against both. Titan V2 on Bedrock (plan 06).
embedding_dimension = 1024

models = {
  classify  = "anthropic/claude-haiku-5.5"
  facts     = "anthropic/claude-haiku-5.5"
  reply     = "anthropic/claude-haiku-5.5"
  fallback  = "openai/gpt-6-luna"
  embedding = "amazon.titan-embed-text-v2:0"
}

# Account Lambda concurrency quota is 10, so nothing can be reserved yet (AWS keeps 10
# unreserved). After a quota increase, set concurrency to cap parallel requests, e.g. 5.
lambda = {
  runtime     = "python3.14"
  memory_mb   = 512
  timeout_s   = 30
  concurrency = -1
}
