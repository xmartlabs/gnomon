# General variables
variable "region" {
  description = "Region where the infrastructure will be hosted (us-east-2, us-east-1, etc)"
  type        = string
}

variable "env" {
  description = "Name of the environment we are managing (staging, rc, production)"
}

variable "project" {
  description = "The name of the project"
}

variable "amiid" {
  description = "The amiid used by the instance"
}

variable "key_name" {
  description = "Key to be used by the EC2"
  default     = "default-key_name"
}

variable "instance_type" {
  description = "Instance type for the EC2"
  default     = "t2.micro"
}

variable "root_disk_volume_size" {
  description = "Root disk volume size"
  default     = "100"
}

variable "create_eip" {
  description = "variable to define if you want to create an elastic ip for the EC2 instance"
  default     = false
}

# To be run after creation
variable "create_machine_script" {
  description = "Path of the start machine script"
}

variable "iam_instance_profile" {
  description = "I am instace profile used in the ec2 instance"
  default     = null
}

variable "subnet_id" {
  description = "Id of the network (public or private) used by the EC2 instance"
}

variable "vpc_id" {
  description = "Id of the VPC used by the EC2 instance"
}
