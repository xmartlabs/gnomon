########### GENERICS ###########
region     = "us-east-2"
env        = "production"
project    = "project_name"

########### VPC ###########
cidr_block         = "172.25.0.0/16"
availability_zones = ["us-east-2a", "us-east-2b"]
public_subnets     = ["172.25.100.0/24", "172.25.101.0/24"]
private_subnets    = ["172.25.0.0/24", "172.25.1.0/24"]

######### RDS ###########
secret_password_id      = "production/db-credentials"
db_name                 = "postgres"
engine                  = "postgres"
engine_version          = "13.11"
rds_storage             = "20"
rds_instance_class      = "db.t3.micro"
backup_retention_period = 7

######### S3 #########
cors_allowed_methods = ["GET"]
cors_allowed_origins = ["*"]

######### EC2 #########
key_name = "ec2-key-name"
# Check that the amiid selected belongs to the region configured
amiid                 = "ami-09694bfab577e90b0"
instance_type         = "t2.micro"
root_disk_volume_size = 100

######### ECR #########
ecr_repositories = [{ "name" = "ecr_rep", "max_images" = 5 }]

######### ACM ########
domain_name = "yourdomain.example.con"

######### ECS ########
discovery_domain_name = "domain.example.com"

######### ECS SERVICE #########
example_service_name      = "example"
example_app               = "example"
example_ecs_desired_count = 1
example_max_capacity      = 1
example_min_capacity      = 1
example_ecr_repo_name     = "ecr_rep"
example_cpu_amount        = 512
example_memory_amount     = 1024
example_docker_port       = 9000
example_image_tag         = "latest"
example_use_load_balancer = true
example_var_file          = "environments/production/files/envs.json"
example_secrets_file      = "environments/production/files/secrets.json"

######### LOAD BALANCER EXAMPLE #########
example_health_check_path = "/"
example_matcher           = "200"
example_enable_tls        = false

######### CACHE ###########
cache_node_type      = "cache.t4g.micro"
num_cache_nodes      = 1
parameter_group_name = "default.redis7"
cache_engine_version = "7.0"
cache_port           = 6379
elasticache_engine   = "redis"

######### AWS BACKUP #########

backup_vault_name = "my-vault"
backup_plan_name  = "my-backup-plan"
backup_tags = {
    Environment = "DEV"
    Project     = "example"
  }

########  KMS ############

create_kms = true
description           = "My KMS key"
enable_key_rotation   = true
deletion_window_in_days = 30
alias                 = "my-alias"
principal_arns        = ["arn:aws:iam::721133465773:user/leomar"]
