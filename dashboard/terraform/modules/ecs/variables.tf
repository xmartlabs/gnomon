variable "region" {
  description = "Region where the infrastructure will be hosted (us-east-2, us-east-1, etc)"
}

variable "env" {
  description = "Name of the environment we are managing (staging, rc, production)"
}

variable "project" {
  description = "The name of the project"
}

variable "vpc_id" {
  description = "Id for the cluster VPC"
}


variable "public_subnets" {
  description = "List of public subnets"
}

variable "private_subnets" {
  description = "List of private subnets"
}

variable "discovery_domain_name" {
  description = "Domain used by the cluster services"
}

variable "container_insights" {
  description = "Boolean variable for enabling or disabling the container insights"
  default     = "disabled"
}
