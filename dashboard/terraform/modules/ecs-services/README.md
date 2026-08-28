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
    	 app  = 
    	 aws_service_discovery_private_dns_namespace  = 
    	 cluster_id  = 
    	 cluster_name  = 
    	 cpu_amount  = 
    	 docker_port  = 
    	 ecr_repo_name  = 
    	 ecs_desired_count  = 
    	 efs_access_point_id  = 
    	 efs_file_system_id  = 
    	 env  = 
    	 max_capacity  = 
    	 memory_amount  = 
    	 min_capacity  = 
    	 private_subnets  = 
    	 project  = 
    	 public_subnets  = 
    	 region  = 
    	 secrets_file  = 
    	 service_name  = 
    	 var_file  = 
    	 vpc_id  = 
    
	 # Optional variables
    	 autoscaling_cpu_target  = 80
    	 autoscaling_ram_target  = 80
    	 capacity_provider  = "FARGATE"
    	 circuit_breaker_enabled  = true
    	 cmd  = ""
    	 discovery_name  = null
    	 image_tag  = "latest"
    	 include_efs_volume  = false
    	 load_balancer_security_group_id  = null
    	 load_balancer_target_group  = null
    	 rollback_enabled  = true
    	 use_autodiscovery  = false
    	 use_load_balancer  = false
  }
```
## Resources

| Name | Type |
|------|------|
| [aws_appautoscaling_policy.ecs_policy_cpu_service_1](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/appautoscaling_policy) | resource |
| [aws_appautoscaling_policy.ecs_policy_memory_service_1](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/appautoscaling_policy) | resource |
| [aws_appautoscaling_target.ecs_target_task-def](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/appautoscaling_target) | resource |
| [aws_cloudwatch_log_group.log-group](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudwatch_log_group) | resource |
| [aws_ecs_service.aws-ecs](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ecs_service) | resource |
| [aws_ecs_task_definition.aws-ecs-task](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ecs_task_definition) | resource |
| [aws_iam_policy.ecs_exec_policy](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_policy) | resource |
| [aws_iam_policy.ecs_exec_ssm_policy](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_policy) | resource |
| [aws_iam_policy.ssm_policy](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_policy) | resource |
| [aws_iam_policy_attachment.ecs_exec](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_policy_attachment) | resource |
| [aws_iam_policy_attachment.ecs_exec_ssm](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_policy_attachment) | resource |
| [aws_iam_policy_attachment.test-attach](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_policy_attachment) | resource |
| [aws_iam_role.ecs-task-execution-role](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role) | resource |
| [aws_iam_role_policy_attachment.ecs-task-execution-role_policy](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy_attachment) | resource |
| [aws_security_group.backend-security-group](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/security_group) | resource |
| [aws_service_discovery_service.service-discovery](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/service_discovery_service) | resource |
| [aws_ecr_repository.repository](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/ecr_repository) | data source |
| [aws_ecs_task_definition.task-def](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/ecs_task_definition) | data source |
| [aws_iam_policy_document.assume-role-policy](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/iam_policy_document) | data source |
| [template_file.env_vars](https://registry.terraform.io/providers/hashicorp/template/latest/docs/data-sources/file) | data source |
| [template_file.secrets_vars](https://registry.terraform.io/providers/hashicorp/template/latest/docs/data-sources/file) | data source |
## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_app"></a> [app](#input\_app) | Name of the app | `any` | n/a | yes |
| <a name="input_autoscaling_cpu_target"></a> [autoscaling\_cpu\_target](#input\_autoscaling\_cpu\_target) | CPU target condition for autoscale the service | `number` | `80` | no |
| <a name="input_autoscaling_ram_target"></a> [autoscaling\_ram\_target](#input\_autoscaling\_ram\_target) | RAM target condition for autoscale the service | `number` | `80` | no |
| <a name="input_aws_service_discovery_private_dns_namespace"></a> [aws\_service\_discovery\_private\_dns\_namespace](#input\_aws\_service\_discovery\_private\_dns\_namespace) | Name of the private hosted zone | `any` | n/a | yes |
| <a name="input_capacity_provider"></a> [capacity\_provider](#input\_capacity\_provider) | Choose between FARGATE or FARGATE\_SPOT | `string` | `"FARGATE"` | no |
| <a name="input_circuit_breaker_enabled"></a> [circuit\_breaker\_enabled](#input\_circuit\_breaker\_enabled) | Boolean flag to enable/disable ecs circuit braker | `bool` | `true` | no |
| <a name="input_cluster_id"></a> [cluster\_id](#input\_cluster\_id) | ECS custer id where the service will be executed | `any` | n/a | yes |
| <a name="input_cluster_name"></a> [cluster\_name](#input\_cluster\_name) | Name of the ECS cluster | `any` | n/a | yes |
| <a name="input_cmd"></a> [cmd](#input\_cmd) | cmd to execute with your task definition | `string` | `""` | no |
| <a name="input_cpu_amount"></a> [cpu\_amount](#input\_cpu\_amount) | Amount of CPU to be used with this task | `any` | n/a | yes |
| <a name="input_discovery_name"></a> [discovery\_name](#input\_discovery\_name) | dns name for your service | `any` | `null` | no |
| <a name="input_docker_port"></a> [docker\_port](#input\_docker\_port) | Port for the container | `any` | n/a | yes |
| <a name="input_ecr_repo_name"></a> [ecr\_repo\_name](#input\_ecr\_repo\_name) | Name for the ECR repositoy used by the service | `any` | n/a | yes |
| <a name="input_ecs_desired_count"></a> [ecs\_desired\_count](#input\_ecs\_desired\_count) | Desired replicas for ecs autoscaling | `any` | n/a | yes |
| <a name="input_efs_access_point_id"></a> [efs\_access\_point\_id](#input\_efs\_access\_point\_id) | n/a | `any` | n/a | yes |
| <a name="input_efs_file_system_id"></a> [efs\_file\_system\_id](#input\_efs\_file\_system\_id) | n/a | `any` | n/a | yes |
| <a name="input_env"></a> [env](#input\_env) | Name of the environment we are managing (staging, rc, production) | `any` | n/a | yes |
| <a name="input_image_tag"></a> [image\_tag](#input\_image\_tag) | Image tag (example: latest | `string` | `"latest"` | no |
| <a name="input_include_efs_volume"></a> [include\_efs\_volume](#input\_include\_efs\_volume) | n/a | `bool` | `false` | no |
| <a name="input_load_balancer_security_group_id"></a> [load\_balancer\_security\_group\_id](#input\_load\_balancer\_security\_group\_id) | Load balancer security group ID . Only required if 'use\_load\_balancer' is set in true | `any` | `null` | no |
| <a name="input_load_balancer_target_group"></a> [load\_balancer\_target\_group](#input\_load\_balancer\_target\_group) | Target group to be used with the service. Only required if 'use\_load\_balancer' is set in true | `any` | `null` | no |
| <a name="input_max_capacity"></a> [max\_capacity](#input\_max\_capacity) | Max replicas for ecs autoscaling | `any` | n/a | yes |
| <a name="input_memory_amount"></a> [memory\_amount](#input\_memory\_amount) | Amount of RAM to be used with this task | `any` | n/a | yes |
| <a name="input_min_capacity"></a> [min\_capacity](#input\_min\_capacity) | Min replicas for ecs autoscaling | `any` | n/a | yes |
| <a name="input_private_subnets"></a> [private\_subnets](#input\_private\_subnets) | List of private subnets | `any` | n/a | yes |
| <a name="input_project"></a> [project](#input\_project) | The name of the project | `any` | n/a | yes |
| <a name="input_public_subnets"></a> [public\_subnets](#input\_public\_subnets) | List of public subnets | `any` | n/a | yes |
| <a name="input_region"></a> [region](#input\_region) | Region where the infrastructure will be hosted (us-east-2, us-east-1, etc) | `any` | n/a | yes |
| <a name="input_rollback_enabled"></a> [rollback\_enabled](#input\_rollback\_enabled) | Boolean flag to enable/disable ecs rollbacks | `bool` | `true` | no |
| <a name="input_secrets_file"></a> [secrets\_file](#input\_secrets\_file) | Secrets file | `any` | n/a | yes |
| <a name="input_service_name"></a> [service\_name](#input\_service\_name) | Name of the service | `any` | n/a | yes |
| <a name="input_use_autodiscovery"></a> [use\_autodiscovery](#input\_use\_autodiscovery) | Whether to use service autodiscovery | `bool` | `false` | no |
| <a name="input_use_load_balancer"></a> [use\_load\_balancer](#input\_use\_load\_balancer) | Whether to use a load balancer for the ECS service | `bool` | `false` | no |
| <a name="input_var_file"></a> [var\_file](#input\_var\_file) | Env variables file | `any` | n/a | yes |
| <a name="input_vpc_id"></a> [vpc\_id](#input\_vpc\_id) | The VPC id used by the service | `any` | n/a | yes |
## Outputs

No outputs.
<!-- END_AUTOMATED_TF_DOCS_BLOCK -->
