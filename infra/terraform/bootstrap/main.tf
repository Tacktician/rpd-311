# bootstrap/main.tf — one-time, run-from-your-laptop stack.
#
# Creates the three things that must exist BEFORE CI can run terraform:
#   1. the S3 bucket holding the main stack's remote state
#   2. the GitHub Actions OIDC provider
#   3. the IAM role GitHub Actions assumes (deploy + teardown)
#
# This stack keeps LOCAL state (bootstrap/terraform.tfstate, gitignored) because it
# owns the bucket the other stack's state lives in — it cannot store state inside a
# bucket it is responsible for creating. It is applied once and then left alone; if
# you lose the local state file, `terraform import` the four resources back (their
# names are deterministic) rather than re-applying.
#
# The teardown workflow destroys the MAIN stack only. Nothing here is torn down, and
# nothing here costs money (an empty versioned S3 bucket and two IAM objects).

terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = "rpd311"
      ManagedBy   = "terraform"
      Stack       = "bootstrap"
      Environment = "shared"
    }
  }
}

data "aws_caller_identity" "current" {}

# ---------------------------------------------------------------------------
# 1. Remote state bucket for the main stack
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "tfstate" {
  bucket = var.state_bucket_name

  # Guards against `terraform destroy` in this directory taking the main stack's
  # state with it. Remove deliberately if you are decommissioning the project.
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "tfstate" {
  bucket                  = aws_s3_bucket.tfstate.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ---------------------------------------------------------------------------
# 2. GitHub Actions OIDC provider
# ---------------------------------------------------------------------------
# One per AWS account. If your account already has it (another repo got there
# first), set `create_oidc_provider = false` and terraform will reuse it.

resource "aws_iam_openid_connect_provider" "github" {
  count = var.create_oidc_provider ? 1 : 0

  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

locals {
  oidc_provider_arn = var.create_oidc_provider ? aws_iam_openid_connect_provider.github[0].arn : "arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/token.actions.githubusercontent.com"
}

# ---------------------------------------------------------------------------
# 3. The role GitHub Actions assumes
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "github_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # Scoped to this repo. `environment:production` covers the deploy and teardown
    # jobs (both declare that environment); the `ref:refs/heads/main` subject covers
    # jobs on main that do not. Anything else in the account cannot assume this role.
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        "repo:${var.github_repo}:environment:production",
        "repo:${var.github_repo}:ref:refs/heads/main",
      ]
    }
  }
}

resource "aws_iam_role" "github_actions" {
  name               = var.ci_role_name
  description        = "RPD 311 — GitHub Actions: terraform apply/destroy, ECR push, EKS deploy"
  assume_role_policy = data.aws_iam_policy_document.github_assume_role.json
}

# The main stack creates and destroys a VPC, an EKS cluster, a node group, the IAM
# roles those need, and ECR repositories. That is a broad blast radius by nature —
# the policy below is scoped by service and, where AWS supports it, by resource name
# prefix. It is deliberately NOT AdministratorAccess.
data "aws_iam_policy_document" "github_actions" {
  # Remote state.
  statement {
    sid       = "TerraformState"
    effect    = "Allow"
    actions   = ["s3:ListBucket", "s3:GetBucketVersioning", "s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = [aws_s3_bucket.tfstate.arn, "${aws_s3_bucket.tfstate.arn}/*"]
  }

  # Cluster + node group lifecycle, and the read calls kubectl/aws-cli need.
  statement {
    sid       = "EKS"
    effect    = "Allow"
    actions   = ["eks:*"]
    resources = ["*"]
  }

  # VPC, subnets, security groups, ENIs, launch templates, instances.
  statement {
    sid       = "EC2Networking"
    effect    = "Allow"
    actions   = ["ec2:*"]
    resources = ["*"]
  }

  # Managed node groups are backed by an ASG that EKS manages on our behalf.
  statement {
    sid       = "AutoScaling"
    effect    = "Allow"
    actions   = ["autoscaling:*"]
    resources = ["*"]
  }

  # The teardown job deletes the NLB that ingress-nginx provisioned; describe calls
  # let it verify the load balancer is really gone before destroying the VPC.
  statement {
    sid       = "LoadBalancers"
    effect    = "Allow"
    actions   = ["elasticloadbalancing:*"]
    resources = ["*"]
  }

  # Image push/pull plus repository lifecycle (terraform owns the repositories).
  statement {
    sid       = "ECR"
    effect    = "Allow"
    actions   = ["ecr:*"]
    resources = ["*"]
  }

  # Cluster and node roles only. Restricted to the project's name prefix so this
  # role cannot mint or modify arbitrary IAM principals.
  statement {
    sid    = "ProjectIAMRoles"
    effect = "Allow"
    actions = [
      "iam:CreateRole",
      "iam:DeleteRole",
      "iam:GetRole",
      "iam:PassRole",
      "iam:TagRole",
      "iam:UntagRole",
      "iam:ListRoleTags",
      "iam:AttachRolePolicy",
      "iam:DetachRolePolicy",
      "iam:ListAttachedRolePolicies",
      "iam:ListRolePolicies",
      "iam:PutRolePolicy",
      "iam:DeleteRolePolicy",
      "iam:GetRolePolicy",
      "iam:CreateServiceLinkedRole",
      "iam:ListInstanceProfilesForRole",
    ]
    resources = [
      "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/${var.project}-*",
      "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/aws-service-role/*",
    ]
  }

  statement {
    sid       = "ReadOnlyLookups"
    effect    = "Allow"
    actions   = ["iam:ListRoles", "iam:ListOpenIDConnectProviders", "sts:GetCallerIdentity", "kms:DescribeKey"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "github_actions" {
  name   = "${var.ci_role_name}-policy"
  role   = aws_iam_role.github_actions.id
  policy = data.aws_iam_policy_document.github_actions.json
}
