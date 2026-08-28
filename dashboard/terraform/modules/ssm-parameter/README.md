<!-- BEGIN_AUTOMATED_TF_DOCS_BLOCK -->
## Requirements

No requirements.
## Usage
Basic usage of this module is as follows:
```hcl
  module "example" {
    	 source  = "<module-path>"
    
	 # Optional variables
    	 parameters  = {}
  }
```
## Resources

| Name | Type |
|------|------|
| [aws_ssm_parameter.params](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ssm_parameter) | resource |
## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_parameters"></a> [parameters](#input\_parameters) | Parameter mapping to be stored in AWS ssm | `map(string)` | `{}` | no |
## Outputs

No outputs.
<!-- END_AUTOMATED_TF_DOCS_BLOCK -->