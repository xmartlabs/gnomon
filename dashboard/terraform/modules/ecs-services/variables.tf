variable "project" {
  description = "The name of the project"
}

variable "env" {
  description = "Name of the environment we are managing (staging, rc, production)"
}

variable "region" {
  description = "Region where the infrastructure will be hosted (us-east-2, us-east-1, etc)"
}

variable "service_name" {
  description = "Name of the service"
}

variable "app" {
  description = "Name of the app"
}

variable "ecs_desired_count" {
  description = "Desired replicas for ecs autoscaling"
}

variable "max_capacity" {
  description = "Max replicas for ecs autoscaling"
}

variable "min_capacity" {
  description = "Min replicas for ecs autoscaling"
}

variable "ecr_repo_name" {
  description = "Name for the ECR repositoy used by the service"
}

variable "cpu_amount" {
  description = "Amount of CPU to be used with this task"
}

variable "memory_amount" {
  description = "Amount of RAM to be used with this task"
}

variable "docker_port" {
  description = "Port for the container"
}

variable "image_tag" {
  description = "Image tag (example: latest"
  default     = "latest"
}

variable "var_file" {
  description = "Env variables file"
}

variable "secrets_file" {
  description = "Secrets file"
}

variable "vpc_id" {
  description = "The VPC id used by the service"
}

variable "public_subnets" {
  description = "List of public subnets"
}

variable "private_subnets" {
  description = "List of private subnets"
}

variable "cluster_id" {
  description = "ECS custer id where the service will be executed"
}

variable "cluster_name" {
  description = "Name of the ECS cluster"
}

variable "use_load_balancer" {
  description = "Whether to use a load balancer for the ECS service"
  type        = bool
  default     = false
}

variable "load_balancer_target_group" {
  description = "Target group to be used with the service. Only required if 'use_load_balancer' is set in true"
  default     = null
}

variable "load_balancer_security_group_id" {
  description = "Load balancer security group ID . Only required if 'use_load_balancer' is set in true"
  default     = null
}

variable "rollback_enabled" {
  description = "Boolean flag to enable/disable ecs rollbacks"
  type        = bool
  default     = true
}

variable "circuit_breaker_enabled" {
  description = "Boolean flag to enable/disable ecs circuit braker"
  type        = bool
  default     = true
}

variable "use_autodiscovery" {
  description = "Whether to use service autodiscovery"
  type        = bool
  default     = false
}

variable "discovery_name" {
  description = "dns name for your service"
  default     = null
}

variable "aws_service_discovery_private_dns_namespace" {
  description = "Name of the private hosted zone"
}

variable "cmd" {
  description = "cmd to execute with your task definition"
  default     = ""
}

variable "autoscaling_cpu_target" {
  description = "CPU target condition for autoscale the service"
  default     = 80
}

variable "autoscaling_ram_target" {
  description = "RAM target condition for autoscale the service"
  default     = 80
}

variable "capacity_provider" {
  description = "Choose between FARGATE or FARGATE_SPOT"
  default     = "FARGATE"
}

variable "efs_file_system_id" {}

variable "efs_access_point_id" {}

variable "include_efs_volume" {
  default = false
}

variable "log_group_retention_in_days" {
  description = "Specifies the number of days you want to retain log events in the specified log group. Possible values are: 1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1096, 1827, 2192, 2557, 2922, 3288, 3653, and 0. If you select 0, the events in the log group are always retained and never expire."
  default     = 30
}

variable "sns_topic_arn" {
  description = "SNS topic to be used to trigger alarms"
  default = null
}

variable "cpu_alarm_threshold" {
  description = "Max CPU alarm threshold"
  type        = number
  default     = 80
}

variable "memory_alarm_threshold" {
  description = "Max memory alarm threshold"
  type        = number
  default     = 80
}

// Task Health Check Variables
variable "task_health_check_command" {
  description = "Command to check the health of the task"
  type        = list(string)
  default     = null
}
variable "task_health_check_interval" {
  description = "Interval to check the health of the task"
  type        = number
  default     = null
}
variable "task_health_check_timeout" {
  description = "Timeout to check the health of the task"
  type        = number
  default     = null
}
variable "task_health_check_retries" {
  description = "Retries to check the health of the task"
  type        = number
  default     = null
}
variable "task_health_check_start_period" {
  description = "Start period to check the health of the task"
  type        = number
  default     = null
}
