output "role_arns" {
  description = "IRSA role ARNs used by runtime components."
  value = {
    rag_server        = module.rag_server_irsa.iam_role_arn
    ingestor_server   = module.ingestor_server_irsa.iam_role_arn
    external_secrets  = module.external_secrets_irsa.iam_role_arn
  }
}
