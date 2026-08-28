```markdown
# AWS Backup Terraform Module

This Terraform module provisions an AWS Backup plan and selection, allowing you to automatically back up AWS resources based on specified tags.

## Usage

To use this module in your Terraform configuration, you need to provide certain mandatory variables and can optionally customize others. Below is an example usage of the module:

```hcl
module "aws_backup" {
  source = "./path_to_module"

  backup_vault_name = "my-backup-vault"
  backup_plan_name  = "my-backup-plan"
  backup_tags       = {
    Environment = "Production"
    Project     = "Project1"
  }
}
```

### Variables

- `backup_vault_name` (string): The name of the AWS Backup vault where the backups will be stored.
- `backup_plan_name` (string): The name of the backup plan.
- `backup_tags` (map(string)): A map of tags used to select the resources to be backed up. Each key-value pair in the map defines one tag that resources must have to be included in the backup.

### Outputs

- `backup_vault_arn`: The ARN of the backup vault.
- `backup_plan_id`: The ID of the backup plan.

### Requirements

- **AWS Provider**: This module uses resources that require the AWS provider.
- **IAM Role**: An IAM role with the necessary permissions for AWS Backup operations must be configured either within the module or externally provided.

### IAM Role Permissions

The IAM role used by AWS Backup must have permissions to manage backups and access the resources you intend to back up. Below is an example policy granting the required permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "backup:*",
        "ec2:DescribeVolumes",
        "ec2:DescribeSnapshots",
        "rds:DescribeDBInstances",
        "rds:DescribeDBSnapshots",
        "dynamodb:ListTables",
        "dynamodb:DescribeTable"
      ],
      "Resource": "*"
    }
  ]
}
```

## Contributing

Contributions to this module are welcome! Please submit pull requests or issues to the repository where this module is maintained.

<!-- BEGIN_AUTOMATED_TF_DOCS_BLOCK -->
## Requirements

No requirements.
## Usage
Basic usage of this module is as follows:
```hcl
  module "example" {
    	 source  = "<module-path>"
    
	 # Required variables
    	 backup_plan_name  = 
    	 backup_vault_name  = 
    
	 # Optional variables
    	 backup_tags  = {
  "Environment": "Production",
  "Project": "Project1"
}
    	 delete_after  = 30
    	 schedule  = "cron(0 5 * * ? *)"
  }
```
## Resources

| Name | Type |
|------|------|
| [aws_backup_plan.example_plan](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/backup_plan) | resource |
| [aws_backup_selection.plan_selection](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/backup_selection) | resource |
| [aws_backup_vault.primary](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/backup_vault) | resource |
| [aws_backup_vault.secondary](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/backup_vault) | resource |
| [aws_iam_policy.backup_policy](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_policy) | resource |
| [aws_iam_role.backup_role](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role) | resource |
| [aws_iam_role_policy_attachment.AWSBackupServiceRolePolicyForBackup](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy_attachment) | resource |
| [aws_iam_role_policy_attachment.AWSBackupServiceRolePolicyForRestores](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy_attachment) | resource |
| [aws_iam_role_policy_attachment.AWSBackupServiceRolePolicyForS3Backup](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy_attachment) | resource |
| [aws_iam_role_policy_attachment.AWSBackupServiceRolePolicyForS3Restore](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy_attachment) | resource |
| [aws_iam_role_policy_attachment.backup_policy_attachment](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy_attachment) | resource |
## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_backup_plan_name"></a> [backup\_plan\_name](#input\_backup\_plan\_name) | Backup plan name | `string` | n/a | yes |
| <a name="input_backup_tags"></a> [backup\_tags](#input\_backup\_tags) | Tags to identify resources to backup | `map(string)` | <pre>{<br>  "Environment": "Production",<br>  "Project": "Project1"<br>}</pre> | no |
| <a name="input_backup_vault_name"></a> [backup\_vault\_name](#input\_backup\_vault\_name) | Backup vaut name | `string` | n/a | yes |
| <a name="input_delete_after"></a> [delete\_after](#input\_delete\_after) | Variable to define how many backups you want to retain | `number` | `30` | no |
| <a name="input_schedule"></a> [schedule](#input\_schedule) | Variable to configure backup frequency | `string` | `"cron(0 5 * * ? *)"` | no |
## Outputs

| Name | Description |
|------|-------------|
| <a name="output_backup_plan_id"></a> [backup\_plan\_id](#output\_backup\_plan\_id) | ID of the backup plan |
| <a name="output_main_backup_vault_arn"></a> [main\_backup\_vault\_arn](#output\_main\_backup\_vault\_arn) | ARN of the main backup vault |
| <a name="output_primary_backup_vault_arn"></a> [primary\_backup\_vault\_arn](#output\_primary\_backup\_vault\_arn) | ARN of the primary backup vault |
| <a name="output_secondary_backup_vault_arn"></a> [secondary\_backup\_vault\_arn](#output\_secondary\_backup\_vault\_arn) | ARN of the secondary backup vault |
<!-- END_AUTOMATED_TF_DOCS_BLOCK -->