variable "env" {
  description = "Name of the environment we are managing (staging, rc, production)"
}

variable "project" {
  description = "The name of the project"
}

# VPC variables
variable "cidr_block" {
  description = "The IPv4 CIDR block for the VPC."
  default     = "10.0.0.0/16"
}

variable "public_subnets" {
  description = "List of IPv4 CIDR blocks used by the public subnets"
}

variable "private_subnets" {
  description = "List of IPv4 CIDR blocks used by the private subnets"
}

variable "availability_zones" {
  description = "List of availability zones used by the subnets"
}
