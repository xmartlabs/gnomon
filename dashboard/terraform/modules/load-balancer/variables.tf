variable "env" {
  description = "Name of the environment we are managing (staging, rc, production)"
}

variable "project" {
  description = "The name of the project"
}

variable "vpc_id" {
  description = "Id of the VPC used by the load balancer"
}

variable "app" {
  description = "Name of the app"
}

variable "public_subnets" {
  description = "List of public subnets"
}

variable "health_check_path" {
  description = "Path where you want the health check to be done"
}

variable "matcher" {
  description = "Status code to be accepted by health check"
}

variable "enable_tls" {
  description = "Habilitar o deshabilitar TLS en el balanceador de carga"
  type        = bool
  default     = false
}

variable "cert_arn" {
  default = null
}

variable "cidr_block" {}

variable "target_group_port" {
  description = "Port for the target group"
  type        = number
  default     = 80
}

variable "target_group_protocol" {
  description = "Protocol for the target group"
  type        = string
  default     = "HTTP"
}

variable "target_group_target_type" {
  description = "Target type for the target group"
  type        = string
  default     = "ip"
}

variable "sns_alert_topic_arn" {
  description = "SNS topic to be used to trigger alarms"
  default     = null
}
