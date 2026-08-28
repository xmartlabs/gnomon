output "primary_backup_vault_arn" {
  description = "ARN of the primary backup vault"
  value       = aws_backup_vault.primary.arn
}

output "secondary_backup_vault_arn" {
  description = "ARN of the secondary backup vault"
  value       = aws_backup_vault.secondary.arn
}

output "main_backup_vault_arn" {
  description = "ARN of the main backup vault"
  value       = aws_backup_vault.primary.arn
}

output "backup_plan_id" {
  description = "ID of the backup plan"
  value       = aws_backup_plan.example_plan.id
}

