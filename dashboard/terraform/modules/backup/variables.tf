variable "backup_vault_name" {
  type        = string
  description = "Backup vaut name"
}

variable "backup_plan_name" {
  type        = string
  description = "Backup plan name"
}

variable "schedule" {
    description = "Variable to configure backup frequency"
    default = "cron(0 5 * * ? *)"  # Every day at 5 AM UTC
}

variable "delete_after" {
    description = "Variable to define how many backups you want to retain"
    default = 30
}

variable "backup_tags" {
  type        = map(string)
  description = "Tags to identify resources to backup"
  default     = {
    Environment = "Production"
    Project     = "Project1"
  }
}

