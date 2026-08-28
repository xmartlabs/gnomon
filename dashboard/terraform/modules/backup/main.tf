provider "aws" {
  alias  = "primary"
  region = var.primary_region
}

provider "aws" {
  alias  = "secondary"
  region = var.secondary_region
}

resource "aws_backup_vault" "primary" {
  provider = aws.primary
  name     = var.primary_vault_name
  tags = {
    Name = "Primary Backup Vault"
  }
}

resource "aws_backup_vault" "secondary" {
  provider = aws.secondary
  name     = var.secondary_vault_name
  tags = {
    Name = "Secondary Backup Vault"
  }
}

resource "aws_backup_selection" "plan_selection" {
  iam_role_arn = aws_iam_role.backup_role.arn
  plan_id      = aws_backup_plan.example_plan.id

  dynamic "selection_tag" {
    for_each = var.backup_tags

    content {
      type  = "STRINGEQUALS"
      key   = selection_tag.key
      value = selection_tag.value
    }
  }

  name = "tag-based-selection"
}

resource "aws_backup_plan" "example_plan" {
  name = var.backup_plan_name

  rule {
    rule_name         = var.backup_rule_name
    target_vault_name = aws_backup_vault.primary.name
    schedule          = var.backup_schedule

    lifecycle {
      delete_after = var.primary_vault_lifecycle.delete_after
    }

    copy_action {
      destination_vault_arn = aws_backup_vault.secondary.arn
      lifecycle {
        delete_after = var.secondary_vault_lifecycle.delete_after
      }
    }
  }
}