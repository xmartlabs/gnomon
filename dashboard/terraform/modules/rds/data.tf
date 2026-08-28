data "aws_secretsmanager_secret_version" "secret_password_rds" {
  secret_id = var.secret_password_id
}
