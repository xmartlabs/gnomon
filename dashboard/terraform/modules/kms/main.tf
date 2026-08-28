resource "aws_kms_key" "this" {
  count                  = var.enabled ? 1 : 0
  description            = var.description
  enable_key_rotation    = var.enable_key_rotation
  deletion_window_in_days = var.deletion_window_in_days

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "Enable IAM User Permissions"
        Effect   = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      {
        Sid      = "Allow use of the key"
        Effect   = "Allow"
        Principal = {
          AWS = var.principal_arns
        }
        Action   = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:ReEncrypt*",
          "kms:GenerateDataKey*",
          "kms:DescribeKey"
        ]
        Resource = "*"
      },
      {
        Sid      = "Allow attachment of persistent resources"
        Effect   = "Allow"
        Principal = {
          AWS = var.principal_arns
        }
        Action   = [
          "kms:CreateGrant",
          "kms:ListGrants",
          "kms:RevokeGrant"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_kms_alias" "this" {
  count         = var.enabled ? 1 : 0
  name          = "alias/${var.alias}"
  target_key_id = aws_kms_key.this[0].id
}

data "aws_caller_identity" "current" {}
