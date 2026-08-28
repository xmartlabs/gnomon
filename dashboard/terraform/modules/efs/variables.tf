variable "env" {
  description = "Name of the environment we are managing (staging, rc, production)"
}

variable "project" {
  description = "The name of the project"
}

variable "vpc_id" {
  description = "Variable for VPC ID"
}

variable "subnet_ids" {
  description = "List of subnet IDs for the EFS mount targets"
  type        = list(string)
}

variable "efs_encrypted" {
    description = "Set to true if you want your EFS to be encrypted"
    default = false
}

variable "efs_performance_mode" {
    description = "Varible to define performance mode, you can choose one of generalPurpose or maxIO"
    default = "generalPurpose"
}

variable "efs_path" {
    description = "Path on the EFS file system to expose as the root directory to NFS clients using the access point to access the EFS file system"
    default = "/"
}

variable "owner_gid" {
    description = "POSIX group ID to apply to the root_directory"
    default = 1000
}

variable "owner_uid" {
    description = "POSIX user ID to apply to the root_directory"
    default = 1000
}

variable "permissions" {
    description = "POSIX permissions to apply to the RootDirectory, in the format of an octal number representing the file's mode bits"
    default = 755
}
variable "access_point_uid" {
    description = "POSIX user ID used for all file system operations using this access point"
    default = 1000
}

variable "access_point_gid" {
    description = "POSIX group ID used for all file system operations using this access point."
    default = 1000
}