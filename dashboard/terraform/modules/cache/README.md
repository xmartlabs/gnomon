<!-- BEGIN_AUTOMATED_TF_DOCS_BLOCK -->
## Requirements

No requirements.
## Usage
Basic usage of this module is as follows:
```hcl
  module "example" {
    	 source  = "<module-path>"
    
	 # Required variables
    	 cache_engine_version  = 
    	 cache_node_type  = 
    	 cache_port  = 
    	 cidr_block  = 
    	 elasticache_engine  = 
    	 env  = 
    	 num_cache_nodes  = 
    	 parameter_group_name  = 
    	 private_subnets  = 
    	 project  = 
    	 vpc_id  = 
  }
```
## Resources

| Name | Type |
|------|------|
| [aws_elasticache_cluster.cache](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/elasticache_cluster) | resource |
| [aws_elasticache_subnet_group.subnet_group_cache](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/elasticache_subnet_group) | resource |
| [aws_security_group.cache_sg](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/security_group) | resource |
## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_cache_engine_version"></a> [cache\_engine\_version](#input\_cache\_engine\_version) | Version number of the cache engine to be used | `any` | n/a | yes |
| <a name="input_cache_node_type"></a> [cache\_node\_type](#input\_cache\_node\_type) | Node Type used by the cache cluster | `any` | n/a | yes |
| <a name="input_cache_port"></a> [cache\_port](#input\_cache\_port) | The port number on which each of the cache nodes will accept connections. For Memcached the default is 11211, and for Redis the default port is 6379. | `any` | n/a | yes |
| <a name="input_cidr_block"></a> [cidr\_block](#input\_cidr\_block) | VPC cidr block | `any` | n/a | yes |
| <a name="input_elasticache_engine"></a> [elasticache\_engine](#input\_elasticache\_engine) | Name of the cache engine to be used for this cache cluster. Valid values are 'memcached' or 'redis' | `any` | n/a | yes |
| <a name="input_env"></a> [env](#input\_env) | Name of the environment we are managing (staging, rc, production) | `any` | n/a | yes |
| <a name="input_num_cache_nodes"></a> [num\_cache\_nodes](#input\_num\_cache\_nodes) | Number of nodes used by the cache cluster | `any` | n/a | yes |
| <a name="input_parameter_group_name"></a> [parameter\_group\_name](#input\_parameter\_group\_name) | The name of the parameter group to associate with this cache cluster. | `any` | n/a | yes |
| <a name="input_private_subnets"></a> [private\_subnets](#input\_private\_subnets) | List of private subnets used by cache | `any` | n/a | yes |
| <a name="input_project"></a> [project](#input\_project) | The name of the project | `any` | n/a | yes |
| <a name="input_vpc_id"></a> [vpc\_id](#input\_vpc\_id) | Variable for VPC ID | `any` | n/a | yes |
## Outputs

No outputs.
<!-- END_AUTOMATED_TF_DOCS_BLOCK -->