terraform {
  # 1.10+ for S3 native state locking (`use_lockfile`) — no DynamoDB table needed.
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }

  # Partial backend configuration — the bucket is created by ./bootstrap and passed
  # in at init time so this file has no account-specific values in it:
  #
  #   terraform init \
  #     -backend-config="bucket=$TF_STATE_BUCKET" \
  #     -backend-config="region=$AWS_REGION"
  #
  # Remote state is what makes the teardown workflow safe: `terraform destroy` writes
  # the emptied state straight back to S3, so the next deploy starts from a clean slate
  # instead of trying to adopt resources that no longer exist.
  backend "s3" {
    key          = "rpd311/prod/terraform.tfstate"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = var.project
      ManagedBy   = "terraform"
      Stack       = "prod"
      Environment = "prod"
    }
  }
}

data "aws_caller_identity" "current" {}

data "aws_availability_zones" "available" {
  state = "available"

  filter {
    name   = "opt-in-status"
    values = ["opt-in-not-required"]
  }
}

locals {
  cluster_name = "${var.project}-${var.environment}"

  # EKS requires subnets in at least two AZs.
  azs = slice(data.aws_availability_zones.available.names, 0, 2)
}
