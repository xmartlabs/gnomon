variable "env" {
  description = "Name of the environment we are managing (staging, rc, production)"
}

variable "project" {
  description = "The name of the project"
}

variable "region" {
  description = "Region where the infrastructure will be hosted (us-east-2, us-east-1, etc)"
}
