<!-- BEGIN_AUTOMATED_TF_DOCS_BLOCK -->
## Requirements

No requirements.
## Usage
Basic usage of this module is as follows:
```hcl
module "example" {
	 source  = "<module-path>"

	 # Required variables
	 amiid  = 
	 create_machine_script  = 
	 env  = 
	 project  = 
	 region  = 
	 subnet_id  = 
	 vpc_id  = 

	 # Optional variables
	 create_eip  = false
	 iam_instance_profile  = null
	 instance_type  = "t2.micro"
	 key_name  = "default-key_name"
	 root_disk_volume_size  = "100"
}
```
## Resources

| Name | Type |
|------|------|
| [aws_eip.eip](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/eip) | resource |
| [aws_instance.ec2-instance](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/instance) | resource |
| [aws_security_group.security_group](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/security_group) | resource |
## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_amiid"></a> [amiid](#input\_amiid) | The amiid used by the instance | `any` | n/a | yes |
| <a name="input_create_eip"></a> [create\_eip](#input\_create\_eip) | variable to define if you want to create an elastic ip for the EC2 instance | `bool` | `false` | no |
| <a name="input_create_machine_script"></a> [create\_machine\_script](#input\_create\_machine\_script) | Path of the start machine script | `any` | n/a | yes |
| <a name="input_env"></a> [env](#input\_env) | Name of the environment we are managing (staging, rc, production) | `any` | n/a | yes |
| <a name="input_iam_instance_profile"></a> [iam\_instance\_profile](#input\_iam\_instance\_profile) | I am instace profile used in the ec2 instance | `any` | `null` | no |
| <a name="input_instance_type"></a> [instance\_type](#input\_instance\_type) | Instance type for the EC2 | `string` | `"t2.micro"` | no |
| <a name="input_key_name"></a> [key\_name](#input\_key\_name) | Key to be used by the EC2 | `string` | `"default-key_name"` | no |
| <a name="input_project"></a> [project](#input\_project) | The name of the project | `any` | n/a | yes |
| <a name="input_region"></a> [region](#input\_region) | Region where the infrastructure will be hosted (us-east-2, us-east-1, etc) | `any` | n/a | yes |
| <a name="input_root_disk_volume_size"></a> [root\_disk\_volume\_size](#input\_root\_disk\_volume\_size) | Root disk volume size | `string` | `"100"` | no |
| <a name="input_subnet_id"></a> [subnet\_id](#input\_subnet\_id) | Id of the network (public or private) used by the EC2 instance | `any` | n/a | yes |
| <a name="input_vpc_id"></a> [vpc\_id](#input\_vpc\_id) | Id of the VPC used by the EC2 instance | `any` | n/a | yes |
## Outputs

| Name | Description |
|------|-------------|
| <a name="output_public_ip"></a> [public\_ip](#output\_public\_ip) | n/a |
| <a name="output_server_id"></a> [server\_id](#output\_server\_id) | n/a |
| <a name="output_server_private_ip"></a> [server\_private\_ip](#output\_server\_private\_ip) | n/a |
<!-- END_AUTOMATED_TF_DOCS_BLOCK -->