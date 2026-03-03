locals {
  managed_secrets = {
    ngc_api_key                     = "/${var.secret_prefix}/${var.environment}/ngc_api_key"
    llm_api_key                     = "/${var.secret_prefix}/${var.environment}/llm_api_key"
    embeddings_api_key              = "/${var.secret_prefix}/${var.environment}/embeddings_api_key"
    ranking_api_key                 = "/${var.secret_prefix}/${var.environment}/ranking_api_key"
    query_rewriter_api_key          = "/${var.secret_prefix}/${var.environment}/query_rewriter_api_key"
    filter_expression_api_key       = "/${var.secret_prefix}/${var.environment}/filter_expression_api_key"
    vlm_api_key                     = "/${var.secret_prefix}/${var.environment}/vlm_api_key"
    summary_llm_api_key             = "/${var.secret_prefix}/${var.environment}/summary_llm_api_key"
    reflection_llm_api_key          = "/${var.secret_prefix}/${var.environment}/reflection_llm_api_key"
  }
}

resource "aws_secretsmanager_secret" "managed" {
  for_each = local.managed_secrets

  name                    = each.value
  description             = "KORDA RAG ${var.environment} secret for ${each.key}"
  kms_key_id              = var.kms_key_arn
  recovery_window_in_days = 7
  tags                    = var.tags
}
