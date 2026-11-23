resource "aws_s3vectors_vector_bucket" "main" {
  vector_bucket_name = "${local.name_prefix}-vectors"
  force_destroy      = var.env != "prod" # dev can be torn down; prod refuses while it holds vectors
}

# Response Cache: keyed on the embedded normalised claim. The answer card rides along as
# non-filterable metadata. Every other metadata key (confidence, cards_category) is
# filterable by default, so weak entries can be found and removed.
resource "aws_s3vectors_index" "response_cache" {
  vector_bucket_name = aws_s3vectors_vector_bucket.main.vector_bucket_name
  index_name         = "response-cache"
  data_type          = "float32"
  dimension          = var.embedding_dimension
  distance_metric    = "cosine"

  metadata_configuration {
    non_filterable_metadata_keys = ["answer_card", "claim"]
  }
}

# Fact Sources: one vector per chunk. source_id stays filterable.
resource "aws_s3vectors_index" "sources" {
  vector_bucket_name = aws_s3vectors_vector_bucket.main.vector_bucket_name
  index_name         = "sources"
  data_type          = "float32"
  dimension          = var.embedding_dimension
  distance_metric    = "cosine"

  metadata_configuration {
    non_filterable_metadata_keys = ["chunk_text", "citation_url", "title"]
  }
}
