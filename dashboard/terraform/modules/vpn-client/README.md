In order to create a new VPN. You need to follow this guide:

https://docs.aws.amazon.com/vpn/latest/clientvpn-admin/cvpn-getting-started.html

STEP 1(Create certs): Do it manually.

STEP 2, 3, 4, 5, 6 Are managed by terraform (Create all AWS resources needed basically).

In order to deploy with terraform, you will need to gather information of your account such as:

Certs ARN after you import them to ACM.

VPC ID.

Security group that you want to use with the VPN.

Subnet ID (The subnet where you want the vpn client to connect).

STEP 7 (Add certs to ovpn file): Do it manually.
<!-- BEGIN_AUTOMATED_TF_DOCS_BLOCK -->
## Requirements

No requirements.
## Usage
Basic usage of this module is as follows:
```hcl
  module "example" {
    	 source  = "<module-path>"
    
	 # Required variables
    	 cloudwatch_log_group  = 
    	 cloudwatch_log_stream  = 
    	 description  = 
    	 root_certificate_chain_arn  = 
    	 security_group_ids  = 
    	 server_certificate_arn  = 
    	 subnet_id  = 
    	 vpc_id  = 
    	 vpn_name  = 
    
	 # Optional variables
    	 dns_servers  = []
    	 environment  = "dev"
    	 region  = "us-east-1"
    	 split_tunnel  = true
    	 target_network_cidr  = "10.0.0.0/16"
    	 transport_protocol  = "udp"
    	 vpn_cidr_block  = "10.200.0.0/22"
  }
```
## Resources

| Name | Type |
|------|------|
| [aws_cloudwatch_log_group.vpn_log_group](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudwatch_log_group) | resource |
| [aws_cloudwatch_log_stream.vpn_log_stream](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudwatch_log_stream) | resource |
| [aws_ec2_client_vpn_authorization_rule.example_vpn](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ec2_client_vpn_authorization_rule) | resource |
| [aws_ec2_client_vpn_endpoint.example_vpn](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ec2_client_vpn_endpoint) | resource |
| [aws_ec2_client_vpn_network_association.example_vpn](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ec2_client_vpn_network_association) | resource |
## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_cloudwatch_log_group"></a> [cloudwatch\_log\_group](#input\_cloudwatch\_log\_group) | Name of the CloudWatch log group for connection logs. | `string` | n/a | yes |
| <a name="input_cloudwatch_log_stream"></a> [cloudwatch\_log\_stream](#input\_cloudwatch\_log\_stream) | Name of the CloudWatch log stream for connection logs. | `string` | n/a | yes |
| <a name="input_description"></a> [description](#input\_description) | Description of the VPN client endpoint. | `string` | n/a | yes |
| <a name="input_dns_servers"></a> [dns\_servers](#input\_dns\_servers) | List of DNS servers for the VPN endpoint. | `list(string)` | `[]` | no |
| <a name="input_environment"></a> [environment](#input\_environment) | The environment to deploy resources in. | `string` | `"dev"` | no |
| <a name="input_region"></a> [region](#input\_region) | The AWS region to deploy resources in. | `string` | `"us-east-1"` | no |
| <a name="input_root_certificate_chain_arn"></a> [root\_certificate\_chain\_arn](#input\_root\_certificate\_chain\_arn) | ARN of the root certificate chain for the VPN endpoint. | `string` | n/a | yes |
| <a name="input_security_group_ids"></a> [security\_group\_ids](#input\_security\_group\_ids) | List of security group IDs to associate with the VPN client endpoint. | `list(string)` | n/a | yes |
| <a name="input_server_certificate_arn"></a> [server\_certificate\_arn](#input\_server\_certificate\_arn) | ARN of the server certificate for the VPN endpoint. | `string` | n/a | yes |
| <a name="input_split_tunnel"></a> [split\_tunnel](#input\_split\_tunnel) | Whether to enable split-tunnel for the VPN endpoint. | `bool` | `true` | no |
| <a name="input_subnet_id"></a> [subnet\_id](#input\_subnet\_id) | ID of the subnet to associate the VPN client endpoint with. | `string` | n/a | yes |
| <a name="input_target_network_cidr"></a> [target\_network\_cidr](#input\_target\_network\_cidr) | CIDR block for the VPN client endpoint. | `string` | `"10.0.0.0/16"` | no |
| <a name="input_transport_protocol"></a> [transport\_protocol](#input\_transport\_protocol) | List of transport protocols to enable for the VPN client endpoint. | `string` | `"udp"` | no |
| <a name="input_vpc_id"></a> [vpc\_id](#input\_vpc\_id) | ID of the VPC to associate the VPN client endpoint with. | `string` | n/a | yes |
| <a name="input_vpn_cidr_block"></a> [vpn\_cidr\_block](#input\_vpn\_cidr\_block) | CIDR block for the VPN client endpoint. | `string` | `"10.200.0.0/22"` | no |
| <a name="input_vpn_name"></a> [vpn\_name](#input\_vpn\_name) | Name for the VPN client endpoint. | `string` | n/a | yes |
## Outputs

| Name | Description |
|------|-------------|
| <a name="output_vpn_client_endpoint_arn"></a> [vpn\_client\_endpoint\_arn](#output\_vpn\_client\_endpoint\_arn) | The ARN of the VPN client endpoint. |
| <a name="output_vpn_client_endpoint_id"></a> [vpn\_client\_endpoint\_id](#output\_vpn\_client\_endpoint\_id) | The ID of the VPN client endpoint. |
<!-- END_AUTOMATED_TF_DOCS_BLOCK -->