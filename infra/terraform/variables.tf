variable "region" {
  description = "AWS region for the cluster."
  type        = string
  default     = "us-east-1"
}

variable "project" {
  description = "Name prefix for every resource. Must match the bootstrap stack's `project` (the CI role's IAM policy is scoped to it)."
  type        = string
  default     = "rpd311"
}

variable "environment" {
  description = "Environment suffix. The cluster is named \"<project>-<environment>\"."
  type        = string
  default     = "prod"
}

variable "vpc_cidr" {
  description = "CIDR for the cluster VPC."
  type        = string
  default     = "10.42.0.0/16"
}

variable "kubernetes_version" {
  description = <<-EOT
    EKS control plane version. Keep this within the AWS standard support window —
    extended support is billed at roughly 6x the control plane rate.
  EOT
  type        = string
  default     = "1.32"
}

variable "node_instance_types" {
  description = <<-EOT
    Instance types for the managed node group. t3.medium (2 vCPU / 4 GiB) fits the
    whole stack: three app services plus in-cluster Postgres, Redis, LocalStack, and
    the ingress-nginx controller. Do not go below t3.small — the pod-per-node limit
    on smaller types will leave pods Pending.
  EOT
  type        = list(string)
  default     = ["t3.medium"]
}

variable "node_desired_size" {
  description = "Nodes at steady state. Two gives the reports-service HPA (2–6 replicas) somewhere to scale."
  type        = number
  default     = 2
}

variable "node_min_size" {
  description = "Minimum node count."
  type        = number
  default     = 2
}

variable "node_max_size" {
  description = "Maximum node count. No cluster-autoscaler is installed, so this is a ceiling for manual scaling only."
  type        = number
  default     = 4
}

variable "node_disk_size" {
  description = "EBS root volume size per node, in GiB."
  type        = number
  default     = 30
}

variable "cluster_endpoint_public_access_cidrs" {
  description = <<-EOT
    CIDRs allowed to reach the public Kubernetes API endpoint. Defaults to open,
    because GitHub Actions runners have no stable egress IP range worth pinning.
    Authentication is still required — this is a network-level narrowing only.
    Tighten it if you only ever run terraform and kubectl from known networks.
  EOT
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "admin_principal_arns" {
  description = <<-EOT
    Extra IAM principals granted cluster-admin via EKS access entries — put your own
    user/role ARN here so `aws eks update-kubeconfig` works from your laptop. The CI
    role gets admin automatically as the cluster creator.
    Example: ["arn:aws:iam::123456789012:user/james.tacker"]
  EOT
  type        = list(string)
  default     = []
}

variable "services" {
  description = "Service names. Each gets an ECR repository; the list must match the directories under services/."
  type        = list(string)
  default     = ["reports-service", "triage-service", "status-service"]
}

variable "ecr_image_retention_count" {
  description = "Number of images to keep per repository. Older ones are expired by lifecycle policy."
  type        = number
  default     = 10
}
