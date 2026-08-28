variable "parameters" {
  description = "Parameter mapping to be stored in AWS ssm"
  type        = map(string)
  default     = {}
}
