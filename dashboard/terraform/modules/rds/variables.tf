variable "env" {
  description = "Name of the environment we are managing (staging, rc, production)"
}

variable "project" {
  description = "The name of the project"
}

variable "vpc_id" {
  description = "Variable for VPC ID"
}

variable "private_subnets" {
  description = "List of private subnets used by RDS"
}

variable "identifier" {
  description = "identifier of the database"
}

variable "cidr_block" {
  description = "VPC cidr block"
}

variable "secret_password_id" {
  description = "Name of the secret where the RDS credentials are stored. It needs to exist and have the keys `username` and `password`"
}

variable "db_name" {
  description = "Database name"
}

variable "engine" {
  description = "Database engine"
}

variable "engine_version" {
  description = "Version of the engine to be used"
}

variable "rds_storage" {
  description = "RDS disk size"
}

variable "rds_instance_class" {
  description = "Instance size for RDS"
}

variable "backup_retention_period" {
  description = "RDS backups retention period in days"
  default     = 7
}

variable "rds_public" {
  description = "Is the RDS publicly accesible?"
  default     = false
}

variable "enable_read_replica" {
  description = "Whether to create a read replica"
  type        = bool
  default     = false
}

variable "multi_az_enabled" {
  description = "Whether to create a read replica"
  type        = bool
  default     = false
}

variable "performance_insights_enabled" {
  description = "performance insights enabled?"
  type        = bool
  default     = false
}

variable "monitoring_interval" {
  description = "performance insights enabled?"
  default     = 60
}

variable "performance_insights_retention_period" {
  description = "performance insights retention period"
  default     = 7
}

variable "disk_queue_depth_alarm_threshold" {
  description = "Disk queue depth alarm threshold"
  type        = number
  default     = 64
}

variable "free_storage_alarm_threshold" {
  description = "Free storage alarm threshold"
  type        = number
  default     = 10 * 1024 * 1024 * 1024 # 10 GB in bytes
}

variable "connections_alarm_threshold" {
  description = "Connections alarm threshold"
  type        = number
  default     = 90
}

variable "sns_topic_arn" {
  description = "SNS topic to be used to trigger alarms"
  default     = null
}
