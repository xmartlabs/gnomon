module "vpc" {
  source             = "./modules/vpc"
  env                = var.env
  project            = var.project
  availability_zones = var.availability_zones
  private_subnets    = var.private_subnets
  public_subnets     = var.public_subnets
  cidr_block         = var.cidr_block
}

module "rds" {
  source                       = "./modules/rds"
  project                      = var.project
  env                          = var.env
  vpc_id                       = module.vpc.vpc_id
  private_subnets              = module.vpc.private_subnets
  db_name                      = var.db_name
  secret_password_id           = var.secret_password_id
  engine                       = var.engine
  engine_version               = var.engine_version
  rds_storage                  = var.rds_storage
  rds_instance_class           = var.rds_instance_class
  identifier                   = "${var.project}-${var.env}-db"
  backup_retention_period      = var.backup_retention_period
  cidr_block                   = var.cidr_block
  rds_public                   = var.rds_public
  performance_insights_enabled = var.rds_performance_insights_enabled
}

module "s3" {
  source               = "./modules/s3"
  project              = var.project
  env                  = var.env
  bucket_name          = "${var.project}-${var.env}-bucket-infra"
  cors_allowed_methods = var.cors_allowed_methods
  cors_allowed_origins = var.cors_allowed_origins
}

module "ec2_iam_profile" {
  source  = "./modules/ec2-iam-profile"
  env     = var.env
  project = var.project
  region  = var.region
}

module "ec2" {
  source                = "./modules/ec2"
  region                = var.region
  amiid                 = var.amiid
  env                   = var.env
  project               = var.project
  subnet_id             = module.vpc.public_subnets[0]
  create_machine_script = "create_machine_script.tmpl"
  key_name              = var.key_name
  instance_type         = var.instance_type
  root_disk_volume_size = var.root_disk_volume_size
  vpc_id                = module.vpc.vpc_id
  iam_instance_profile  = module.ec2_iam_profile.ec2_profile_name
}

module "ecr" {
  source           = "./modules/ecr"
  ecr_repositories = var.ecr_repositories
}

module "acm" {
  source      = "./modules/acm"
  domain_name = var.domain_name
  env         = var.env
}

module "ecs" {
  source                = "./modules/ecs"
  project               = var.project
  env                   = var.env
  region                = var.region
  vpc_id                = module.vpc.vpc_id
  public_subnets        = module.vpc.public_subnets
  private_subnets       = module.vpc.private_subnets
  discovery_domain_name = var.discovery_domain_name
}

module "ecs_service_example" {
  source                                      = "./modules/ecs-services"
  project                                     = var.project
  env                                         = var.env
  region                                      = var.region
  service_name                                = var.example_service_name
  app                                         = var.example_app
  ecs_desired_count                           = var.example_ecs_desired_count
  max_capacity                                = var.example_max_capacity
  min_capacity                                = var.example_min_capacity
  ecr_repo_name                               = var.example_ecr_repo_name
  cpu_amount                                  = var.example_cpu_amount
  memory_amount                               = var.example_memory_amount
  docker_port                                 = var.example_docker_port
  image_tag                                   = var.example_image_tag
  var_file                                    = var.example_var_file
  secrets_file                                = var.example_secrets_file
  vpc_id                                      = module.vpc.vpc_id
  public_subnets                              = module.vpc.public_subnets
  private_subnets                             = module.vpc.private_subnets
  cluster_id                                  = module.ecs.cluster_id
  cluster_name                                = module.ecs.cluster_name
  use_load_balancer                           = var.example_use_load_balancer
  load_balancer_target_group                  = module.example_load_balancer.load_balancer_target_group
  load_balancer_security_group_id             = module.example_load_balancer.load_balancer_security_group_id
  rollback_enabled                            = var.example_rollback_enabled
  circuit_breaker_enabled                     = var.example_circuit_breaker_enabled
  aws_service_discovery_private_dns_namespace = module.ecs.aws_service_discovery_private_dns_namespace
  use_autodiscovery                           = var.example_use_autodiscovery
  discovery_name                              = var.example_discovery_name
  cmd                                         = var.example_cmd
  include_efs_volume                          = var.include_efs_volume         # Use this if you need a volume in your ECS Service. 
  efs_access_point_id                         = module.efs.efs_access_point_id # Parameter for EFS Volume 
  efs_file_system_id                          = module.efs.efs_file_system_id  # Parameter for EFS Volume
  depends_on                                  = [module.ecs]
}

module "example_load_balancer" {
  source            = "./modules/load-balancer"
  project           = var.project
  env               = var.env
  app               = var.example_app
  vpc_id            = module.vpc.vpc_id
  public_subnets    = module.vpc.public_subnets
  health_check_path = var.example_health_check_path
  matcher           = var.example_matcher
  enable_tls        = var.example_enable_tls
  cidr_block        = var.cidr_block
  cert_arn          = module.acm.cert_arn
}

module "cache" {
  source               = "./modules/cache"
  project              = var.project
  env                  = var.env
  private_subnets      = module.vpc.private_subnets
  cache_node_type      = var.cache_node_type
  num_cache_nodes      = var.num_cache_nodes
  parameter_group_name = var.parameter_group_name
  cache_engine_version = var.cache_engine_version
  cache_port           = var.cache_port
  elasticache_engine   = var.elasticache_engine
  vpc_id               = module.vpc.vpc_id
  cidr_block           = var.cidr_block
}

module "ssm_parameters" {
  source     = "./modules/ssm-parameter"
  parameters = var.parameters
}

module "efs" {
  source     = "./modules/efs"
  project    = var.project
  env        = var.env
  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets
}

module "aws_backup" {
  source                    = "./modules/backup"
  primary_region            = var.primary_region
  secondary_region          = var.secondary_region
  primary_vault_name        = var.primary_vault_name
  secondary_vault_name      = var.secondary_vault_name
  backup_rule_name          = var.backup_rule_name
  backup_schedule           = var.schedule
  primary_vault_lifecycle   = { delete_after = 10 }
  secondary_vault_lifecycle = { delete_after = 15 }
  backup_vault_name         = var.backup_vault_name
  backup_plan_name          = var.backup_plan_name
  backup_tags               = var.backup_tags
  schedule                  = var.schedule
}

module "vpn_client" {
  source                     = "./modules/vpn-client"
  region                     = var.primary_region
  description                = "VPN to access resources in a private way"
  root_certificate_chain_arn = var.root_certificate_chain_arn
  server_certificate_arn     = var.server_certificate_arn
  cloudwatch_log_group       = var.cloudwatch_log_group
  cloudwatch_log_stream      = var.cloudwatch_log_stream
  dns_servers                = var.dns_servers
  split_tunnel               = var.split_tunnel
  vpc_id                     = var.vpc_id
  subnet_id                  = var.subnet_id
  security_group_ids         = var.security_groups_ids
  transport_protocol         = var.transport_protocol
  vpn_cidr_block             = var.vpn_cidr_block
  vpn_name                   = var.vpn_name
}

module "kms" {
  source                  = "./modules/kms"
  enabled                 = var.create_kms
  description             = var.description
  enable_key_rotation     = var.enable_key_rotation
  deletion_window_in_days = var.deletion_window_in_days
  alias                   = var.alias
  principal_arns          = var.principal_arns
}
