# ecr.tf — one repository per service.
#
# Repositories are named "rpd311/<service>", matching the local image names the
# minikube path uses (rpd311/reports-service:1.0.0) so the only difference between
# environments is the registry prefix.

resource "aws_ecr_repository" "services" {
  for_each = toset(var.services)

  name = "${var.project}/${each.value}"

  # Images are rebuilt from source on every push to main, so nothing here is
  # irreplaceable — let the teardown workflow delete repositories that still have
  # images in them instead of failing.
  force_delete = true

  image_scanning_configuration {
    scan_on_push = true
  }

  # Deploys pin an immutable :<sha> tag, so nothing needs to overwrite a tag.
  image_tag_mutability = "IMMUTABLE"

  tags = {
    Name    = "${var.project}/${each.value}"
    Service = each.value
  }
}

resource "aws_ecr_lifecycle_policy" "services" {
  for_each = aws_ecr_repository.services

  repository = each.value.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep the ${var.ecr_image_retention_count} most recent images; expire the rest."
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = var.ecr_image_retention_count
        }
        action = { type = "expire" }
      },
    ]
  })
}
