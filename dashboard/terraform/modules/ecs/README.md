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
    	 discovery_domain_name  = 
    	 env  = 
    	 private_subnets  = 
    	 project  = 
    	 public_subnets  = 
    	 region  = 
    	 vpc_id  = 
    
	 # Optional variables
    	 container_insights  = "disabled"
  }
```
## Resources

| Name | Type |
|------|------|
| [aws_ecs_cluster.aws-ecs-cluster](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ecs_cluster) | resource |
| [aws_ecs_cluster_capacity_providers.example](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ecs_cluster_capacity_providers) | resource |
| [aws_service_discovery_private_dns_namespace.segment](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/service_discovery_private_dns_namespace) | resource |
## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_container_insights"></a> [container\_insights](#input\_container\_insights) | Boolean variable for enabling or disabling the container insights | `string` | `"disabled"` | no |
| <a name="input_discovery_domain_name"></a> [discovery\_domain\_name](#input\_discovery\_domain\_name) | Domain used by the cluster services | `any` | n/a | yes |
| <a name="input_env"></a> [env](#input\_env) | Name of the environment we are managing (staging, rc, production) | `any` | n/a | yes |
| <a name="input_private_subnets"></a> [private\_subnets](#input\_private\_subnets) | List of private subnets | `any` | n/a | yes |
| <a name="input_project"></a> [project](#input\_project) | The name of the project | `any` | n/a | yes |
| <a name="input_public_subnets"></a> [public\_subnets](#input\_public\_subnets) | List of public subnets | `any` | n/a | yes |
| <a name="input_region"></a> [region](#input\_region) | Region where the infrastructure will be hosted (us-east-2, us-east-1, etc) | `any` | n/a | yes |
| <a name="input_vpc_id"></a> [vpc\_id](#input\_vpc\_id) | Id for the cluster VPC | `any` | n/a | yes |
## Outputs

| Name | Description |
|------|-------------|
| <a name="output_aws_service_discovery_private_dns_namespace"></a> [aws\_service\_discovery\_private\_dns\_namespace](#output\_aws\_service\_discovery\_private\_dns\_namespace) | DNS namespace |
| <a name="output_cluster_id"></a> [cluster\_id](#output\_cluster\_id) | ECS cluster id |
| <a name="output_cluster_name"></a> [cluster\_name](#output\_cluster\_name) | Name of the cluster |
<!-- END_AUTOMATED_TF_DOCS_BLOCK -->
