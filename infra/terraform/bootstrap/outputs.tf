output "state_bucket" {
  description = "Pass to the main stack as -backend-config=bucket=..."
  value       = aws_s3_bucket.tfstate.id
}

output "state_bucket_region" {
  description = "Pass to the main stack as -backend-config=region=..."
  value       = var.region
}

output "ci_role_arn" {
  description = "Set as the AWS_ROLE_ARN repo variable (Settings → Secrets and variables → Actions → Variables)."
  value       = aws_iam_role.github_actions.arn
}

output "next_steps" {
  description = "Repo configuration required before the deploy job will run."
  value       = <<-EOT

    Bootstrap complete. Configure the repo (Settings → Secrets and variables → Actions):

      Variables:
        AWS_ROLE_ARN      = ${aws_iam_role.github_actions.arn}
        AWS_REGION        = ${var.region}
        TF_STATE_BUCKET   = ${aws_s3_bucket.tfstate.id}

      Secrets:
        SERVICE_TOKEN     = <a long random string; the X-Service-Token shared secret>
        POSTMAN_API_KEY   = <optional; only needed for the Insights Agent lessons>

    The deploy job self-skips until AWS_ROLE_ARN and TF_STATE_BUCKET are both set,
    so CI stays green in the meantime.
  EOT
}
