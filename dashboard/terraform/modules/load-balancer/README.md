<!-- BEGIN_AUTOMATED_TF_DOCS_BLOCK -->
## Requirements

No requirements.
## Usage
Basic usage of this module is as follows:
```hcl
  module "example" {
    	 source  = "<module-path>"
    
	 # Required variables
    	 app  = 
    	 cidr_block  = 
    	 env  = 
    	 health_check_path  = 
    	 matcher  = 
    	 project  = 
    	 public_subnets  = 
    	 vpc_id  = 
    
	 # Optional variables
    	 cert_arn  = null
    	 enable_tls  = false
  }
```
## Resources

| Name | Type |
|------|------|
| [aws_alb.application-load-balancer](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/alb) | resource |
| [aws_lb_listener.listener_service_legacy](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lb_listener) | resource |
| [aws_lb_listener.listener_service_legacy_tls](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lb_listener) | resource |
| [aws_lb_listener.redirect_http](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lb_listener) | resource |
| [aws_lb_target_group.target-group](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lb_target_group) | resource |
| [aws_security_group.load-balancer-security-group](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/security_group) | resource |
## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_app"></a> [app](#input\_app) | Name of the app | `any` | n/a | yes |
| <a name="input_cert_arn"></a> [cert\_arn](#input\_cert\_arn) | n/a | `any` | `null` | no |
| <a name="input_cidr_block"></a> [cidr\_block](#input\_cidr\_block) | n/a | `any` | n/a | yes |
| <a name="input_enable_tls"></a> [enable\_tls](#input\_enable\_tls) | Habilitar o deshabilitar TLS en el balanceador de carga | `bool` | `false` | no |
| <a name="input_env"></a> [env](#input\_env) | Name of the environment we are managing (staging, rc, production) | `any` | n/a | yes |
| <a name="input_health_check_path"></a> [health\_check\_path](#input\_health\_check\_path) | Path where you want the health check to be done | `any` | n/a | yes |
| <a name="input_matcher"></a> [matcher](#input\_matcher) | Status code to be accepted by health check | `any` | n/a | yes |
| <a name="input_project"></a> [project](#input\_project) | The name of the project | `any` | n/a | yes |
| <a name="input_public_subnets"></a> [public\_subnets](#input\_public\_subnets) | List of public subnets | `any` | n/a | yes |
| <a name="input_vpc_id"></a> [vpc\_id](#input\_vpc\_id) | Id of the VPC used by the load balancer | `any` | n/a | yes |
## Outputs

| Name | Description |
|------|-------------|
| <a name="output_alb"></a> [alb](#output\_alb) | ECS ALB |
| <a name="output_load_balancer_security_group_id"></a> [load\_balancer\_security\_group\_id](#output\_load\_balancer\_security\_group\_id) | Load balancer target group |
| <a name="output_load_balancer_target_group"></a> [load\_balancer\_target\_group](#output\_load\_balancer\_target\_group) | Load balancer target group |
<!-- END_AUTOMATED_TF_DOCS_BLOCK -->