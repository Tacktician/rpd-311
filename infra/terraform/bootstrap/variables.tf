variable "region" {
  description = "AWS region for the state bucket. Does not have to match the cluster region, but there is no reason to differ."
  type        = string
  default     = "us-east-1"
}

variable "project" {
  description = "Name prefix for project-owned IAM roles. Must match the main stack's `project` variable."
  type        = string
  default     = "rpd311"
}

variable "state_bucket_name" {
  description = <<-EOT
    Globally unique S3 bucket name for the main stack's terraform state.
    S3 bucket names are shared across all AWS accounts, so add something unique
    (your account ID works well): "rpd311-tfstate-123456789012".
  EOT
  type        = string
}

variable "github_repo" {
  description = "owner/repo allowed to assume the CI role, e.g. \"Tacktician/rpd-311\"."
  type        = string
}

variable "ci_role_name" {
  description = "Name of the IAM role GitHub Actions assumes. Its ARN becomes the AWS_ROLE_ARN repo variable."
  type        = string
  default     = "rpd311-github-actions"
}

variable "create_oidc_provider" {
  description = "Create the GitHub Actions OIDC provider. Set false if this AWS account already has one (only one is allowed per account)."
  type        = bool
  default     = true
}
