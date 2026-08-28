output "key_id" {
  description = "The ID of the KMS key"
  value       = aws_kms_key.this[0].id
}

output "key_arn" {
  description = "The ARN of the KMS key"
  value       = aws_kms_key.this[0].arn
}

output "alias_name" {
  description = "The alias name of the KMS key"
  value       = aws_kms_alias.this[0].name
}

output "alias_arn" {
  description = "The ARN of the KMS alias"
  value       = aws_kms_alias.this[0].arn
}
