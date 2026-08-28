resource "aws_ecr_repository" "ecr_repository" {
  for_each = { for record in var.ecr_repositories : record.name => record }
  name     = lower("${each.value.name}")
}

resource "aws_ecr_lifecycle_policy" "ecr_lifecycle_policy" {
  for_each   = { for record in var.ecr_repositories : record.name => record }
  repository = each.value.name
  depends_on = [aws_ecr_repository.ecr_repository]
  policy     = <<-EOF
{
    "rules": [
        {
            "rulePriority": 1,
            "description": "Keep last N images",
            "selection": {
                "tagStatus": "any",
                "countType": "imageCountMoreThan",
                "countNumber": ${each.value.max_images}
            },
            "action": {
                "type": "expire"
            }
        }
    ]
}
  EOF
}
