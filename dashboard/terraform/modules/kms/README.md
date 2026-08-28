<!-- BEGIN_AUTOMATED_TF_DOCS_BLOCK -->
## Requirements

No requirements.
## Usage
Basic usage of this module is as follows:
```hcl
  module "example" {
    	 source  = "<module-path>"
    
	 # Optional variables
    	 alias  = "my-key-alias"
    	 deletion_window_in_days  = 30
    	 description  = "KMS key for encryption"
    	 enable_key_rotation  = true
    	 enabled  = true
    	 principal_arns  = []
  }
```
## Resources

| Name | Type |
|------|------|
| [aws_kms_alias.this](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/kms_alias) | resource |
| [aws_kms_key.this](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/kms_key) | resource |
| [aws_caller_identity.current](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/caller_identity) | data source |
## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_alias"></a> [alias](#input\_alias) | The alias name for the KMS key | `string` | `"my-key-alias"` | no |
| <a name="input_deletion_window_in_days"></a> [deletion\_window\_in\_days](#input\_deletion\_window\_in\_days) | Specifies the number of days in the deletion window | `number` | `30` | no |
| <a name="input_description"></a> [description](#input\_description) | The description of the KMS key | `string` | `"KMS key for encryption"` | no |
| <a name="input_enable_key_rotation"></a> [enable\_key\_rotation](#input\_enable\_key\_rotation) | Specifies whether key rotation is enabled | `bool` | `true` | no |
| <a name="input_enabled"></a> [enabled](#input\_enabled) | Whether the KMS key should be created | `bool` | `true` | no |
| <a name="input_principal_arns"></a> [principal\_arns](#input\_principal\_arns) | The ARNs of the principals (users, roles) that will be allowed to use the key | `list(string)` | `[]` | no |
## Outputs

| Name | Description |
|------|-------------|
| <a name="output_alias_arn"></a> [alias\_arn](#output\_alias\_arn) | The ARN of the KMS alias |
| <a name="output_alias_name"></a> [alias\_name](#output\_alias\_name) | The alias name of the KMS key |
| <a name="output_key_arn"></a> [key\_arn](#output\_key\_arn) | The ARN of the KMS key |
| <a name="output_key_id"></a> [key\_id](#output\_key\_id) | The ID of the KMS key |
<!-- END_AUTOMATED_TF_DOCS_BLOCK -->