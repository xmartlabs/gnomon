
# General variables
variable "region" {
  description = "Region where the infrastructure will be hosted (us-east-2, us-east-1, etc)"
  type        = string
}

variable "env" {
  description = "Name of the environment we are managing (staging, rc, production)"
  type        = string
}
variable "app" {
  default = "dev"
}
variable "project" {
  description = "The name of the project"
}

# VPC variables
variable "cidr_block" {
  description = "The IPv4 CIDR block for the VPC."
  default     = "10.0.0.0/16"
}

variable "public_subnets" {
  description = "List of IPv4 CIDR blocks used by the public subnets"
}

variable "private_subnets" {
  description = "List of IPv4 CIDR blocks used by the private subnets"
}

variable "availability_zones" {
  description = "List of availability zones used by the subnets"
}

# RDS variables
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

variable "rds_performance_insights_enabled" {
  description = "Is the RDS performance insights enabled?"
  default     = true
}

# S3 Variables
variable "cors_allowed_methods" {
  description = "Allowed methods"
}

variable "cors_allowed_origins" {
  description = "Allowed origins"
}

# EC2 variables
variable "amiid" {
  description = "The amiid used by the instance"
}

variable "key_name" {
  description = "Key to be used by the EC2"
  default     = "default-key_name"
}

variable "instance_type" {
  description = "Instance type for the EC2"
  default     = "t2.micro"
}

variable "root_disk_volume_size" {
  description = "Root disk volume size"
  default     = "100"
}

# ECR variables
variable "ecr_repositories" {
  description = "List of ECR repositories to create. The format of each repository needs to be a dict with the keys `name` and `max_images`"
  default     = []
}

# ACM variables
variable "domain_name" {
  description = "Domain name to be used"
}

# ECS Variables
variable "discovery_domain_name" {
  description = "Domain used by the cluster services"
}

variable "container_insights" {
  description = "Boolean variable for enabling or disabling the container insights"
  default     = "disabled"
}

# ECS Service variables
variable "example_service_name" {
  description = "Name of the service"
}

variable "example_app" {
  description = "Name of the app"
}

variable "example_ecs_desired_count" {
  description = "Desired replicas for ecs autoscaling"
}

variable "example_max_capacity" {
  description = "Max replicas for ecs autoscaling"
}

variable "example_min_capacity" {
  description = "Min replicas for ecs autoscaling"
}

variable "example_ecr_repo_name" {
  description = "Name for the ECR repositoy used by the service"
}

variable "example_cpu_amount" {
  description = "Amount of CPU to be used with this task"
}

variable "example_memory_amount" {
  description = "Amount of RAM to be used with this task"
}

variable "example_docker_port" {
  description = "Port for the container"
}

variable "example_image_tag" {
  description = "Image tag (example: latest"
  default     = "latest"
}

variable "example_var_file" {
  description = "Env variables file"
}

variable "example_secrets_file" {
  description = "Secrets file"
}

variable "example_use_load_balancer" {
  description = "Whether to use a load balancer for the ECS service"
  type        = bool
  default     = false
}

variable "example_rollback_enabled" {
  description = "Boolean flag to enable/disable ecs rollbacks"
  type        = bool
  default     = true
}

variable "example_circuit_breaker_enabled" {
  description = "Boolean flag to enable/disable ecs circuit braker"
  type        = bool
  default     = true
}

variable "example_use_autodiscovery" {
  description = "Whether to use service autodiscovery"
  type        = bool
  default     = false
}
variable "example_discovery_name" {
  description = "dns name for your service"
  default     = null
}

variable "example_cmd" {
  description = "cmd to execute with your task definition"
  default     = ""
}

variable "example_autoscaling_cpu_target" {
  description = "CPU target condition for autoscale the service"
  default     = 80
}

variable "example_autoscaling_ram_target" {
  description = "RAM target condition for autoscale the service"
  default     = 80
}

variable "example_capacity_provider" {
  description = "Choose between FARGATE or FARGATE_SPOT"
  default     = "FARGATE"
}

variable "include_efs_volume" {
  description = "Variable to add a volume (EFS) to your ECS service"
  default     = false
}

# Load balancer Variables
variable "example_health_check_path" {
  description = "Path where you want the health check to be done"
}

variable "example_matcher" {
  description = "Status code to be accepted by health check"
}

variable "example_enable_tls" {
  description = "Habilitar o deshabilitar TLS en el balanceador de carga"
  type        = bool
  default     = false
}

variable "example_cert_arn" {
  default = null
}

# Cache Variables
variable "parameter_group_name" {
  description = "The name of the parameter group to associate with this cache cluster."
}

variable "cache_engine_version" {
  description = "Version number of the cache engine to be used"
}

variable "cache_port" {
  description = "The port number on which each of the cache nodes will accept connections. For Memcached the default is 11211, and for Redis the default port is 6379."
}

variable "cache_node_type" {
  description = "Node Type used by the cache cluster"
}

variable "num_cache_nodes" {
  description = "Number of nodes used by the cache cluster"
}

variable "elasticache_engine" {
  description = "Name of the cache engine to be used for this cache cluster. Valid values are 'memcached' or 'redis'"
}

# SSM Variables
variable "parameters" {
  description = "Parameter mapping to be stored in AWS ssm"
  type        = map(string)
  default     = {}
}

#AWS BACKUP

variable "primary_vault_name" {
  description = "Name for the primary backup vault"
  type        = string
  default     = "primary-backup-vault"
}

variable "secondary_vault_name" {
  description = "Name for the secondary backup vault"
  type        = string
  default     = "secondary-backup-vault"
}

variable "backup_plan_name" {
  description = "Name of your backup plan"
}

variable "backup_tags" {
  type        = map(string)
  description = "Tags to identify resources to backup"
  default = {
    Environment = "Dev"
    Project     = "Example"
  }
}

variable "schedule" {
  description = "Variable to configure backup frequency"
  default     = "cron(0 13 * * ? *)" # Every day at 1 PM UTC
}

variable "backup_rule_name" {
  description = "Name for the backup rule"
  type        = string
  default     = "example-backup-rule"
}

variable "backup_vault_name" {
  description = "Name for the main backup vault"
  type        = string
}

#VPN

variable "root_certificate_chain_arn" {
  description = "ARN for the root certificate"
  type        = string
}
variable "server_certificate_arn" {
  description = "ARN for the server certificate"
  type        = string
}
variable "cloudwatch_log_group" {
  description = "Name for the cloudwatch log group"
  type        = string
}
variable "cloudwatch_log_stream" {
  description = "Name for the cloudwatch log stream"
  type        = string
}
variable "dns_servers" {
  description = "List of DNS servers to use for the VPN connection"
  type        = list(string)
  default     = ["8.8.8.8", "10.0.0.2"]
}
variable "split_tunnel" {
  description = "Boolean to indicate whether to enable split tunneling or not"
  type        = bool
  default     = true
}
variable "vpc_id" {
  description = "VPC ID"
  type        = string
}
variable "subnet_id" {
  description = "Subnet ID"
  type        = string
}
variable "security_groups_ids" {
  description = "Security groups"
  type        = list(string)
}
variable "transport_protocol" {
  description = "Transport protocol to use for the VPN connection"
  type        = string
  default     = "udp"
}

variable "vpn_cidr_block" {
  description = "CIDR block for the VPN client endpoint."
  default     = "10.200.0.0/22"
}
variable "vpn_name" {
  description = "Name for the VPN client endpoint."
  type        = string
}

variable "vpn_session_timeout_hours" {
  description = "The maximum session duration is a trigger by which end-users are required to re-authenticate prior to establishing a VPN session. Valid values: 8 | 10 | 12 | 24"
  type        = number
  default     = 8
}

variable "vpn_disconnect_on_session_timeout" {
  description = "Indicates whether the client VPN session is disconnected after the maximum session_timeout_hours is reached"
  type        = bool
  default     = true
}

variable "vpn_log_group_retention_in_days" {
  description = "Specifies the number of days you want to retain log events in the specified log group. Possible values are: 1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1096, 1827, 2192, 2557, 2922, 3288, 3653, and 0. If you select 0, the events in the log group are always retained and never expire."
  type        = number
  default     = 30
}

#KMS 

variable "create_kms" {
  description = "Whether to create the KMS key"
  type        = bool
  default     = false
}

variable "description" {
  description = "The description of the KMS key"
  type        = string
  default     = "KMS key for encryption"
}

variable "enable_key_rotation" {
  description = "Specifies whether key rotation is enabled"
  type        = bool
  default     = true
}

variable "deletion_window_in_days" {
  description = "Specifies the number of days in the deletion window"
  type        = number
  default     = 30
}

variable "alias" {
  description = "The alias name for the KMS key"
  type        = string
  default     = "my-key-alias"
}

variable "principal_arns" {
  description = "The ARNs of the principals (users, roles) that will be allowed to use the key"
  type        = list(string)
  default     = []
}
