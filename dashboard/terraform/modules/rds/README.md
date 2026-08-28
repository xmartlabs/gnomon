<!-- BEGIN_AUTOMATED_TF_DOCS_BLOCK -->
## Requirements

| Name | Version |
|------|---------|
| <a name="requirement_terraform"></a> [terraform](#requirement\_terraform) | >= 1.3 |
## Usage
Basic usage of this module is as follows:
```hcl
  module "example" {
    	 source  = "<module-path>"
    
	 # Required variables
    	 cidr_block  = 
    	 db_name  = 
    	 engine  = 
    	 engine_version  = 
    	 env  = 
    	 identifier  = 
    	 private_subnets  = 
    	 project  = 
    	 rds_instance_class  = 
    	 rds_storage  = 
    	 secret_password_id  = 
    	 vpc_id  = 
    
	 # Optional variables
    	 backup_retention_period  = 7
    	 rds_public  = false
  }
```
## Resources

| Name | Type |
|------|------|
| [aws_db_instance.myinstance](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/db_instance) | resource |
| [aws_db_subnet_group.subnetgroup](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/db_subnet_group) | resource |
| [aws_security_group.rds_sg](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/security_group) | resource |
| [aws_secretsmanager_secret_version.secret_password_rds](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/secretsmanager_secret_version) | data source |
## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_backup_retention_period"></a> [backup\_retention\_period](#input\_backup\_retention\_period) | RDS backups retention period in days | `number` | `7` | no |
| <a name="input_cidr_block"></a> [cidr\_block](#input\_cidr\_block) | VPC cidr block | `any` | n/a | yes |
| <a name="input_db_name"></a> [db\_name](#input\_db\_name) | Database name | `any` | n/a | yes |
| <a name="input_engine"></a> [engine](#input\_engine) | Database engine | `any` | n/a | yes |
| <a name="input_engine_version"></a> [engine\_version](#input\_engine\_version) | Version of the engine to be used | `any` | n/a | yes |
| <a name="input_env"></a> [env](#input\_env) | Name of the environment we are managing (staging, rc, production) | `any` | n/a | yes |
| <a name="input_identifier"></a> [identifier](#input\_identifier) | identifier of the database | `any` | n/a | yes |
| <a name="input_private_subnets"></a> [private\_subnets](#input\_private\_subnets) | List of private subnets used by RDS | `any` | n/a | yes |
| <a name="input_project"></a> [project](#input\_project) | The name of the project | `any` | n/a | yes |
| <a name="input_rds_instance_class"></a> [rds\_instance\_class](#input\_rds\_instance\_class) | Instance size for RDS | `any` | n/a | yes |
| <a name="input_rds_public"></a> [rds\_public](#input\_rds\_public) | Is the RDS publicly accesible? | `bool` | `false` | no |
| <a name="input_rds_storage"></a> [rds\_storage](#input\_rds\_storage) | RDS disk size | `any` | n/a | yes |
| <a name="input_secret_password_id"></a> [secret\_password\_id](#input\_secret\_password\_id) | Name of the secret where the RDS credentials are stored. It needs to exist and have the keys `username` and `password` | `any` | n/a | yes |
| <a name="input_vpc_id"></a> [vpc\_id](#input\_vpc\_id) | Variable for VPC ID | `any` | n/a | yes |
## Outputs

| Name | Description |
|------|-------------|
| <a name="output_rds_endpoint"></a> [rds\_endpoint](#output\_rds\_endpoint) | n/a |
<!-- END_AUTOMATED_TF_DOCS_BLOCK -->