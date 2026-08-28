# Terraform Basic Infra

Developed by [Xmartlabs](https://xmartlabs.com/).

## Overview

This repository contains Terraform code designed to deploy a set of infrastructure resources on AWS using modules. By combining these modules, you will be able to deploy solutions ranging from simple setups with a single EC2 instance to complex multi-service solutions utilizing ECS clusters. Some of the resources included in the repository are:

- Elastic Container Service (ECS)
- Elastic Load Balancer
- Relational Database Service (RDS)
- Elasticache (for memcache or redis cache)
- Simple Storage Service (S3)
- Elastic Compute Cloud  (EC2)
- Virtual Private Cloud (VPC)

## Directory Structure

- `main.tf`: The main Terraform configuration file containing module definitions.
- `variables.tf`: Define input variables for the Terraform modules.
- `outputs.tf`: Define output values to be displayed after the Terraform execution.
- `provider.tf`: Configure AWS provider settings.
- `environments/`: Folder that contains the different environment configurations
  - `example/`: Example environment configuration files.
    - `terraform.tfvars`: Variables for the example environment.
- `modules/`
  - `acm/`: ACM module.
  - `backup/`: Backup module.
  - `cache/`: Elasticache module.
  - `ec2/`: EC2 instance.
  - `ec2-iam-profile/`: EC2 Iam profile module. 
  - `ecr/`: Elastic Container Registry module.
  - `ecs/`: ECS module.
  - `ecs-services/`: ECS services module.
  - `efs/`: Amazon Elastic File System module.
  - `kms/`: Key Management Services module.
  - `load-balancer/`: ECS module.
  - `rds/`: RDS module. 
  - `s3/`: S3 module.
  - `ssm-parameter/`: SSM Parameter module.
  - `vpc/`: VPC module.
  - `vpn-client`: VPN client module.
	
## Get Started

### Prerequisites

Before you begin, ensure you have the following prerequisites:

- **AWS Account:** You must have an AWS account and necessary credentials to deploy resources.
- **Terraform:** Ensure Terraform is installed on your local machine. You can download it from [terraform.io](https://www.terraform.io/downloads.html).
- **AWS Client:** Install in your machine the [aws client tool](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) corresponding to your operating system.
- **Terraform docs**: Required for updating the modules documentation if you modify them. You can install the tool from [terraform-docs.io](https://terraform-docs.io/).

### Configure AWS Client in your machine

Before utilizing the template, you need to configure the AWS client on your machine. Here are some recommendations we suggest for doing so:

- Avoid using your user account to execute the Terraform commands. Instead, create an independent user with only the necessary permissions and configure the AWS client with it.

- Refrain from using the default configuration in the client. It's preferable to create a profile specifically for the project.

### Create s3 bucket for backend

In this implementation, we're going to use an s3 bucket as backend for our infrastructure as code.

After validate that you meet all prerequisites. Go to AWS and create an S3 bucket with server-side encryption enabled. (This resource has to be created manually).

We recommend using as bucket name `{account-id}-tfstate`. As the S3 bucket name has to be globally unique, this name is rarely occupied as contents of your account id and makes it intuitive that there is where tfstate is allocated.

### Providers file

After creating the bucket, you need to configure the backend in the `provider.tf` file. To do that, create a backend-config file (an example is provided in the file `config/example-backend-config.properties`) with the following information:

* **bucket=** Place your S3 bucket name here.
* **key=** Specify the name of the tfstate file.
* **region=** Indicate the region where we are going to work. You have to input the value directly since the "provider" block doesn't allow variables.

Once the file is created, initialize the project using it:

```bash
terraform init -backend-config=<config-path>
```

### Workspaces

In order to separate environments, we're going to use **workspaces**. We're going to select the workspace of the environment where we are going to work or create a new one.

To list the existing workspace you can use:
```bash
terraform workspace list
```
To select the workspace:
```bash
terraform workspace select {workspace-name}
```
To create a new workspace:
```bash
terraform workspace new {workspace-name}
```

### Usage

In order to separate the variables of the different environments, we are going to have a different `{environment}.tfvars` file for each one.

```bash
# Validates the syntax
terraform validate
# Evaluates the code with the state to know what is going to be modified
terraform plan -var-file="./environments/{environment}.tfvars"
# Apply the changes
terraform apply -var-file="./environments/{environment}.tfvars"
## You will be prompted to confirm the resource creation. Enter `yes` to proceed.
# Destroy everything
terraform destroy -var-file="./environments/{environment}.tfvars"
```

### Updating the documentation

If you want to modify or add some new modules; remember to execute the terraform format command before commit the changes to keep the configuration in the standard style

```bash
terraform fmt
```

In addition to that, you need to update the documentation executing the command:

```bash
terraform-docs markdown table .
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

Feel free to customize this README according to your project's specific details and requirements. Good luck with your Terraform deployments!

<!-- BEGIN_AUTOMATED_TF_DOCS_BLOCK -->
## Requirements

| Name | Version |
|------|---------|
| <a name="requirement_terraform"></a> [terraform](#requirement\_terraform) | >= 1.3 |
| <a name="requirement_aws"></a> [aws](#requirement\_aws) | ~> 5.16.2 |
## Usage
Basic usage of this module is as follows:
```hcl
  module "example" {
    	 source  = "<module-path>"
    
	 # Required variables
    	 amiid  = 
    	 availability_zones  = 
    	 backup_plan_name  = 
    	 backup_vault_name  = 
    	 cache_engine_version  = 
    	 cache_node_type  = 
    	 cache_port  = 
    	 cloudwatch_log_group  = 
    	 cloudwatch_log_stream  = 
    	 cors_allowed_methods  = 
    	 cors_allowed_origins  = 
    	 db_name  = 
    	 discovery_domain_name  = 
    	 domain_name  = 
    	 elasticache_engine  = 
    	 engine  = 
    	 engine_version  = 
    	 env  = 
    	 example_app  = 
    	 example_cpu_amount  = 
    	 example_docker_port  = 
    	 example_ecr_repo_name  = 
    	 example_ecs_desired_count  = 
    	 example_health_check_path  = 
    	 example_matcher  = 
    	 example_max_capacity  = 
    	 example_memory_amount  = 
    	 example_min_capacity  = 
    	 example_secrets_file  = 
    	 example_service_name  = 
    	 example_var_file  = 
    	 num_cache_nodes  = 
    	 parameter_group_name  = 
    	 private_subnets  = 
    	 project  = 
    	 public_subnets  = 
    	 rds_instance_class  = 
    	 rds_storage  = 
    	 region  = 
    	 root_certificate_chain_arn  = 
    	 secret_password_id  = 
    	 security_groups_ids  = 
    	 server_certificate_arn  = 
    	 subnet_id  = 
    	 vpc_id  = 
    	 vpn_name  = 
    
	 # Optional variables
    	 alias  = "my-key-alias"
    	 app  = "dev"
    	 backup_retention_period  = 7
    	 backup_rule_name  = "example-backup-rule"
    	 backup_tags  = {
  "Environment": "Dev",
  "Project": "Example"
}
    	 cidr_block  = "10.0.0.0/16"
    	 container_insights  = "disabled"
    	 create_kms  = false
    	 deletion_window_in_days  = 30
    	 description  = "KMS key for encryption"
    	 dns_servers  = [
  "8.8.8.8",
  "10.0.0.2"
]
    	 ecr_repositories  = []
    	 enable_key_rotation  = true
    	 example_autoscaling_cpu_target  = 80
    	 example_autoscaling_ram_target  = 80
    	 example_capacity_provider  = "FARGATE"
    	 example_cert_arn  = null
    	 example_circuit_breaker_enabled  = true
    	 example_cmd  = ""
    	 example_discovery_name  = null
    	 example_enable_tls  = false
    	 example_image_tag  = "latest"
    	 example_rollback_enabled  = true
    	 example_use_autodiscovery  = false
    	 example_use_load_balancer  = false
    	 include_efs_volume  = false
    	 instance_type  = "t2.micro"
    	 key_name  = "default-key_name"
    	 parameters  = {}
    	 primary_vault_name  = "primary-backup-vault"
    	 principal_arns  = []
    	 rds_public  = false
    	 root_disk_volume_size  = "100"
    	 schedule  = "cron(0 13 * * ? *)"
    	 secondary_vault_name  = "secondary-backup-vault"
    	 split_tunnel  = true
    	 transport_protocol  = "udp"
    	 vpn_cidr_block  = "10.200.0.0/22"
  }
```
## Resources

No resources.
## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_alias"></a> [alias](#input\_alias) | The alias name for the KMS key | `string` | `"my-key-alias"` | no |
| <a name="input_amiid"></a> [amiid](#input\_amiid) | The amiid used by the instance | `any` | n/a | yes |
| <a name="input_app"></a> [app](#input\_app) | n/a | `string` | `"dev"` | no |
| <a name="input_availability_zones"></a> [availability\_zones](#input\_availability\_zones) | List of availability zones used by the subnets | `any` | n/a | yes |
| <a name="input_backup_plan_name"></a> [backup\_plan\_name](#input\_backup\_plan\_name) | Name of your backup plan | `any` | n/a | yes |
| <a name="input_backup_retention_period"></a> [backup\_retention\_period](#input\_backup\_retention\_period) | RDS backups retention period in days | `number` | `7` | no |
| <a name="input_backup_rule_name"></a> [backup\_rule\_name](#input\_backup\_rule\_name) | Name for the backup rule | `string` | `"example-backup-rule"` | no |
| <a name="input_backup_tags"></a> [backup\_tags](#input\_backup\_tags) | Tags to identify resources to backup | `map(string)` | <pre>{<br>  "Environment": "Dev",<br>  "Project": "Example"<br>}</pre> | no |
| <a name="input_backup_vault_name"></a> [backup\_vault\_name](#input\_backup\_vault\_name) | Name for the main backup vault | `string` | n/a | yes |
| <a name="input_cache_engine_version"></a> [cache\_engine\_version](#input\_cache\_engine\_version) | Version number of the cache engine to be used | `any` | n/a | yes |
| <a name="input_cache_node_type"></a> [cache\_node\_type](#input\_cache\_node\_type) | Node Type used by the cache cluster | `any` | n/a | yes |
| <a name="input_cache_port"></a> [cache\_port](#input\_cache\_port) | The port number on which each of the cache nodes will accept connections. For Memcached the default is 11211, and for Redis the default port is 6379. | `any` | n/a | yes |
| <a name="input_cidr_block"></a> [cidr\_block](#input\_cidr\_block) | The IPv4 CIDR block for the VPC. | `string` | `"10.0.0.0/16"` | no |
| <a name="input_cloudwatch_log_group"></a> [cloudwatch\_log\_group](#input\_cloudwatch\_log\_group) | Name for the cloudwatch log group | `string` | n/a | yes |
| <a name="input_cloudwatch_log_stream"></a> [cloudwatch\_log\_stream](#input\_cloudwatch\_log\_stream) | Name for the cloudwatch log stream | `string` | n/a | yes |
| <a name="input_container_insights"></a> [container\_insights](#input\_container\_insights) | Boolean variable for enabling or disabling the container insights | `string` | `"disabled"` | no |
| <a name="input_cors_allowed_methods"></a> [cors\_allowed\_methods](#input\_cors\_allowed\_methods) | Allowed methods | `any` | n/a | yes |
| <a name="input_cors_allowed_origins"></a> [cors\_allowed\_origins](#input\_cors\_allowed\_origins) | Allowed origins | `any` | n/a | yes |
| <a name="input_create_kms"></a> [create\_kms](#input\_create\_kms) | Whether to create the KMS key | `bool` | `false` | no |
| <a name="input_db_name"></a> [db\_name](#input\_db\_name) | Database name | `any` | n/a | yes |
| <a name="input_deletion_window_in_days"></a> [deletion\_window\_in\_days](#input\_deletion\_window\_in\_days) | Specifies the number of days in the deletion window | `number` | `30` | no |
| <a name="input_description"></a> [description](#input\_description) | The description of the KMS key | `string` | `"KMS key for encryption"` | no |
| <a name="input_discovery_domain_name"></a> [discovery\_domain\_name](#input\_discovery\_domain\_name) | Domain used by the cluster services | `any` | n/a | yes |
| <a name="input_dns_servers"></a> [dns\_servers](#input\_dns\_servers) | List of DNS servers to use for the VPN connection | `list(string)` | <pre>[<br>  "8.8.8.8",<br>  "10.0.0.2"<br>]</pre> | no |
| <a name="input_domain_name"></a> [domain\_name](#input\_domain\_name) | Domain name to be used | `any` | n/a | yes |
| <a name="input_ecr_repositories"></a> [ecr\_repositories](#input\_ecr\_repositories) | List of ECR repositories to create. The format of each repository needs to be a dict with the keys `name` and `max_images` | `list` | `[]` | no |
| <a name="input_elasticache_engine"></a> [elasticache\_engine](#input\_elasticache\_engine) | Name of the cache engine to be used for this cache cluster. Valid values are 'memcached' or 'redis' | `any` | n/a | yes |
| <a name="input_enable_key_rotation"></a> [enable\_key\_rotation](#input\_enable\_key\_rotation) | Specifies whether key rotation is enabled | `bool` | `true` | no |
| <a name="input_engine"></a> [engine](#input\_engine) | Database engine | `any` | n/a | yes |
| <a name="input_engine_version"></a> [engine\_version](#input\_engine\_version) | Version of the engine to be used | `any` | n/a | yes |
| <a name="input_env"></a> [env](#input\_env) | Name of the environment we are managing (staging, rc, production) | `string` | n/a | yes |
| <a name="input_example_app"></a> [example\_app](#input\_example\_app) | Name of the app | `any` | n/a | yes |
| <a name="input_example_autoscaling_cpu_target"></a> [example\_autoscaling\_cpu\_target](#input\_example\_autoscaling\_cpu\_target) | CPU target condition for autoscale the service | `number` | `80` | no |
| <a name="input_example_autoscaling_ram_target"></a> [example\_autoscaling\_ram\_target](#input\_example\_autoscaling\_ram\_target) | RAM target condition for autoscale the service | `number` | `80` | no |
| <a name="input_example_capacity_provider"></a> [example\_capacity\_provider](#input\_example\_capacity\_provider) | Choose between FARGATE or FARGATE\_SPOT | `string` | `"FARGATE"` | no |
| <a name="input_example_cert_arn"></a> [example\_cert\_arn](#input\_example\_cert\_arn) | n/a | `any` | `null` | no |
| <a name="input_example_circuit_breaker_enabled"></a> [example\_circuit\_breaker\_enabled](#input\_example\_circuit\_breaker\_enabled) | Boolean flag to enable/disable ecs circuit braker | `bool` | `true` | no |
| <a name="input_example_cmd"></a> [example\_cmd](#input\_example\_cmd) | cmd to execute with your task definition | `string` | `""` | no |
| <a name="input_example_cpu_amount"></a> [example\_cpu\_amount](#input\_example\_cpu\_amount) | Amount of CPU to be used with this task | `any` | n/a | yes |
| <a name="input_example_discovery_name"></a> [example\_discovery\_name](#input\_example\_discovery\_name) | dns name for your service | `any` | `null` | no |
| <a name="input_example_docker_port"></a> [example\_docker\_port](#input\_example\_docker\_port) | Port for the container | `any` | n/a | yes |
| <a name="input_example_ecr_repo_name"></a> [example\_ecr\_repo\_name](#input\_example\_ecr\_repo\_name) | Name for the ECR repositoy used by the service | `any` | n/a | yes |
| <a name="input_example_ecs_desired_count"></a> [example\_ecs\_desired\_count](#input\_example\_ecs\_desired\_count) | Desired replicas for ecs autoscaling | `any` | n/a | yes |
| <a name="input_example_enable_tls"></a> [example\_enable\_tls](#input\_example\_enable\_tls) | Habilitar o deshabilitar TLS en el balanceador de carga | `bool` | `false` | no |
| <a name="input_example_health_check_path"></a> [example\_health\_check\_path](#input\_example\_health\_check\_path) | Path where you want the health check to be done | `any` | n/a | yes |
| <a name="input_example_image_tag"></a> [example\_image\_tag](#input\_example\_image\_tag) | Image tag (example: latest | `string` | `"latest"` | no |
| <a name="input_example_matcher"></a> [example\_matcher](#input\_example\_matcher) | Status code to be accepted by health check | `any` | n/a | yes |
| <a name="input_example_max_capacity"></a> [example\_max\_capacity](#input\_example\_max\_capacity) | Max replicas for ecs autoscaling | `any` | n/a | yes |
| <a name="input_example_memory_amount"></a> [example\_memory\_amount](#input\_example\_memory\_amount) | Amount of RAM to be used with this task | `any` | n/a | yes |
| <a name="input_example_min_capacity"></a> [example\_min\_capacity](#input\_example\_min\_capacity) | Min replicas for ecs autoscaling | `any` | n/a | yes |
| <a name="input_example_rollback_enabled"></a> [example\_rollback\_enabled](#input\_example\_rollback\_enabled) | Boolean flag to enable/disable ecs rollbacks | `bool` | `true` | no |
| <a name="input_example_secrets_file"></a> [example\_secrets\_file](#input\_example\_secrets\_file) | Secrets file | `any` | n/a | yes |
| <a name="input_example_service_name"></a> [example\_service\_name](#input\_example\_service\_name) | Name of the service | `any` | n/a | yes |
| <a name="input_example_use_autodiscovery"></a> [example\_use\_autodiscovery](#input\_example\_use\_autodiscovery) | Whether to use service autodiscovery | `bool` | `false` | no |
| <a name="input_example_use_load_balancer"></a> [example\_use\_load\_balancer](#input\_example\_use\_load\_balancer) | Whether to use a load balancer for the ECS service | `bool` | `false` | no |
| <a name="input_example_var_file"></a> [example\_var\_file](#input\_example\_var\_file) | Env variables file | `any` | n/a | yes |
| <a name="input_include_efs_volume"></a> [include\_efs\_volume](#input\_include\_efs\_volume) | Variable to add a volume (EFS) to your ECS service | `bool` | `false` | no |
| <a name="input_instance_type"></a> [instance\_type](#input\_instance\_type) | Instance type for the EC2 | `string` | `"t2.micro"` | no |
| <a name="input_key_name"></a> [key\_name](#input\_key\_name) | Key to be used by the EC2 | `string` | `"default-key_name"` | no |
| <a name="input_num_cache_nodes"></a> [num\_cache\_nodes](#input\_num\_cache\_nodes) | Number of nodes used by the cache cluster | `any` | n/a | yes |
| <a name="input_parameter_group_name"></a> [parameter\_group\_name](#input\_parameter\_group\_name) | The name of the parameter group to associate with this cache cluster. | `any` | n/a | yes |
| <a name="input_parameters"></a> [parameters](#input\_parameters) | Parameter mapping to be stored in AWS ssm | `map(string)` | `{}` | no |
| <a name="input_primary_vault_name"></a> [primary\_vault\_name](#input\_primary\_vault\_name) | Name for the primary backup vault | `string` | `"primary-backup-vault"` | no |
| <a name="input_principal_arns"></a> [principal\_arns](#input\_principal\_arns) | The ARNs of the principals (users, roles) that will be allowed to use the key | `list(string)` | `[]` | no |
| <a name="input_private_subnets"></a> [private\_subnets](#input\_private\_subnets) | List of IPv4 CIDR blocks used by the private subnets | `any` | n/a | yes |
| <a name="input_project"></a> [project](#input\_project) | The name of the project | `any` | n/a | yes |
| <a name="input_public_subnets"></a> [public\_subnets](#input\_public\_subnets) | List of IPv4 CIDR blocks used by the public subnets | `any` | n/a | yes |
| <a name="input_rds_instance_class"></a> [rds\_instance\_class](#input\_rds\_instance\_class) | Instance size for RDS | `any` | n/a | yes |
| <a name="input_rds_public"></a> [rds\_public](#input\_rds\_public) | Is the RDS publicly accesible? | `bool` | `false` | no |
| <a name="input_rds_storage"></a> [rds\_storage](#input\_rds\_storage) | RDS disk size | `any` | n/a | yes |
| <a name="input_region"></a> [region](#input\_region) | Region where the infrastructure will be hosted (us-east-2, us-east-1, etc) | `string` | n/a | yes |
| <a name="input_root_certificate_chain_arn"></a> [root\_certificate\_chain\_arn](#input\_root\_certificate\_chain\_arn) | ARN for the root certificate | `string` | n/a | yes |
| <a name="input_root_disk_volume_size"></a> [root\_disk\_volume\_size](#input\_root\_disk\_volume\_size) | Root disk volume size | `string` | `"100"` | no |
| <a name="input_schedule"></a> [schedule](#input\_schedule) | Variable to configure backup frequency | `string` | `"cron(0 13 * * ? *)"` | no |
| <a name="input_secondary_vault_name"></a> [secondary\_vault\_name](#input\_secondary\_vault\_name) | Name for the secondary backup vault | `string` | `"secondary-backup-vault"` | no |
| <a name="input_secret_password_id"></a> [secret\_password\_id](#input\_secret\_password\_id) | Name of the secret where the RDS credentials are stored. It needs to exist and have the keys `username` and `password` | `any` | n/a | yes |
| <a name="input_security_groups_ids"></a> [security\_groups\_ids](#input\_security\_groups\_ids) | Security groups | `list(string)` | n/a | yes |
| <a name="input_server_certificate_arn"></a> [server\_certificate\_arn](#input\_server\_certificate\_arn) | ARN for the server certificate | `string` | n/a | yes |
| <a name="input_split_tunnel"></a> [split\_tunnel](#input\_split\_tunnel) | Boolean to indicate whether to enable split tunneling or not | `bool` | `true` | no |
| <a name="input_subnet_id"></a> [subnet\_id](#input\_subnet\_id) | Subnet ID | `string` | n/a | yes |
| <a name="input_transport_protocol"></a> [transport\_protocol](#input\_transport\_protocol) | Transport protocol to use for the VPN connection | `string` | `"udp"` | no |
| <a name="input_vpc_id"></a> [vpc\_id](#input\_vpc\_id) | VPC ID | `string` | n/a | yes |
| <a name="input_vpn_cidr_block"></a> [vpn\_cidr\_block](#input\_vpn\_cidr\_block) | CIDR block for the VPN client endpoint. | `string` | `"10.200.0.0/22"` | no |
| <a name="input_vpn_name"></a> [vpn\_name](#input\_vpn\_name) | Name for the VPN client endpoint. | `string` | n/a | yes |
## Outputs

| Name | Description |
|------|-------------|
| <a name="output_example_balancer"></a> [example\_balancer](#output\_example\_balancer) | ALB of legacy django |
| <a name="output_rds_endpoint"></a> [rds\_endpoint](#output\_rds\_endpoint) | RDS Endpoint |
| <a name="output_vpc_id"></a> [vpc\_id](#output\_vpc\_id) | VPC ID |
<!-- END_AUTOMATED_TF_DOCS_BLOCK -->
