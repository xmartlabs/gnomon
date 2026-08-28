### README.md for the EFS Terraform Module

---

## Module Overview

This Terraform module is designed to provision Amazon Elastic File System (EFS) resources efficiently. It includes resource creation for EFS file systems, mount targets in multiple subnets, and EFS access points to facilitate easy integration and scalability for applications requiring shared file storage.

## Features

- **EFS File System Creation**: Configures and deploys an EFS file system.
- **Mount Targets**: Automatically sets up mount targets for each provided subnet, allowing EC2 instances in different subnets to access the file system.
- **EFS Access Points**: Creates access points to streamline access and implement file system directory and permission structures.
- **Security Group Configuration**: Establishes a security group for EFS that controls access to the file system.

## Prerequisites

- **AWS Account**: You must have an AWS account with permissions to manage EFS, VPC, and IAM resources.
- **Terraform**: Terraform v0.12.x or newer is required.
- **AWS Provider**: AWS provider version at least v3.x is necessary.

## Usage

To use this module in your Terraform environment, include it in your configuration with the required parameters like so:

```hcl
module "efs" {
  source     = "./modules/efs"
  project           = var.project
  env               = var.env
  vpc_id            = module.vpc.vpc_id
  subnet_ids        = module.vpc.private_subnets             
}
```

Make sure to adjust `path/to/module/efs` to the actual path where the module is located.


## Outputs

| Name                 | Description                               |
|----------------------|-------------------------------------------|
| `efs_access_point_id`| The ID of the EFS Access Point            |
| `efs_file_system_id` | The ID of the EFS File System             |

## Authors

Module managed by Xmartlabs DevOps team.
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
    	 env  = 
    	 project  = 
    	 subnet_ids  = 
    	 vpc_id  = 
    
	 # Optional variables
    	 access_point_gid  = 1000
    	 access_point_uid  = 1000
    	 efs_encrypted  = false
    	 efs_path  = "/"
    	 efs_performance_mode  = "generalPurpose"
    	 owner_gid  = 1000
    	 owner_uid  = 1000
    	 permissions  = 755
  }
```
## Resources

| Name | Type |
|------|------|
| [aws_efs_access_point.my_efs_access_point](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/efs_access_point) | resource |
| [aws_efs_file_system.my_efs](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/efs_file_system) | resource |
| [aws_efs_mount_target.my_efs_mount_targets](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/efs_mount_target) | resource |
| [aws_security_group.efs_sg](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/security_group) | resource |
## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_access_point_gid"></a> [access\_point\_gid](#input\_access\_point\_gid) | POSIX group ID used for all file system operations using this access point. | `number` | `1000` | no |
| <a name="input_access_point_uid"></a> [access\_point\_uid](#input\_access\_point\_uid) | POSIX user ID used for all file system operations using this access point | `number` | `1000` | no |
| <a name="input_efs_encrypted"></a> [efs\_encrypted](#input\_efs\_encrypted) | Set to true if you want your EFS to be encrypted | `bool` | `false` | no |
| <a name="input_efs_path"></a> [efs\_path](#input\_efs\_path) | Path on the EFS file system to expose as the root directory to NFS clients using the access point to access the EFS file system | `string` | `"/"` | no |
| <a name="input_efs_performance_mode"></a> [efs\_performance\_mode](#input\_efs\_performance\_mode) | Varible to define performance mode, you can choose one of generalPurpose or maxIO | `string` | `"generalPurpose"` | no |
| <a name="input_env"></a> [env](#input\_env) | Name of the environment we are managing (staging, rc, production) | `any` | n/a | yes |
| <a name="input_owner_gid"></a> [owner\_gid](#input\_owner\_gid) | POSIX group ID to apply to the root\_directory | `number` | `1000` | no |
| <a name="input_owner_uid"></a> [owner\_uid](#input\_owner\_uid) | POSIX user ID to apply to the root\_directory | `number` | `1000` | no |
| <a name="input_permissions"></a> [permissions](#input\_permissions) | POSIX permissions to apply to the RootDirectory, in the format of an octal number representing the file's mode bits | `number` | `755` | no |
| <a name="input_project"></a> [project](#input\_project) | The name of the project | `any` | n/a | yes |
| <a name="input_subnet_ids"></a> [subnet\_ids](#input\_subnet\_ids) | List of subnet IDs for the EFS mount targets | `list(string)` | n/a | yes |
| <a name="input_vpc_id"></a> [vpc\_id](#input\_vpc\_id) | Variable for VPC ID | `any` | n/a | yes |
## Outputs

| Name | Description |
|------|-------------|
| <a name="output_efs_access_point_id"></a> [efs\_access\_point\_id](#output\_efs\_access\_point\_id) | The ID of the EFS Access Point |
| <a name="output_efs_file_system_id"></a> [efs\_file\_system\_id](#output\_efs\_file\_system\_id) | The ID of the EFS File System |
<!-- END_AUTOMATED_TF_DOCS_BLOCK -->