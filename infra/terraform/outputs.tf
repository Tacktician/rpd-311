output "cluster_name" {
  description = "Feed to `aws eks update-kubeconfig --name`."
  value       = aws_eks_cluster.main.name
}

output "cluster_endpoint" {
  description = "Kubernetes API server endpoint."
  value       = aws_eks_cluster.main.endpoint
}

output "cluster_version" {
  description = "Running control plane version."
  value       = aws_eks_cluster.main.version
}

output "region" {
  description = "Region the cluster runs in."
  value       = var.region
}

output "ecr_registry" {
  description = "Registry host to prefix image tags with."
  value       = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.region}.amazonaws.com"
}

output "ecr_repository_urls" {
  description = "Per-service repository URLs, keyed by service name."
  value       = { for name, repo in aws_ecr_repository.services : name => repo.repository_url }
}

output "vpc_id" {
  description = "Cluster VPC id — useful when hunting orphaned load balancers after a teardown."
  value       = aws_vpc.main.id
}

output "kubeconfig_command" {
  description = "Run this to point kubectl at the cluster."
  value       = "aws eks update-kubeconfig --name ${aws_eks_cluster.main.name} --region ${var.region}"
}
