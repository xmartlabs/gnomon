variable "enabled" {
  description = "Whether the KMS key should be created"
  type        = bool
  default     = true
}

variable "description" {
  description = "The description of the KMS key"
  type        = string
  default     = "KMS key for encryption"
}

variable "enable_key_rotation" {
  description = "Specifies whether key rotation is enabled"
  type        = bool
  default     = true
}

variable "deletion_window_in_days" {
  description = "Specifies the number of days in the deletion window"
  type        = number
  default     = 30
}

variable "alias" {
  description = "The alias name for the KMS key"
  type        = string
  default     = "my-key-alias"
}

variable "principal_arns" {
  description = "The ARNs of the principals (users, roles) that will be allowed to use the key"
  type        = list(string)
  default     = []
}
