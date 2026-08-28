variable "env" {
  description = "Name of the environment we are managing (staging, rc, production)"
}

variable "project" {
  description = "The name of the project"
}

variable "bucket_name" {
  description = "Name of the bucket"
}

variable "block_public_acls" {
  description = "Block public acls"
  default     = true
}

variable "block_public_policy" {
  description = "Block public policy"
  default     = true
}

variable "ignore_public_acls" {
  description = "Ignore public acls"
  default     = true
}

variable "restrict_public_buckets" {
  description = "Restrict public buckets"
  default     = true
}

variable "cors_allowed_methods" {
  description = "CORS Allowed methods"
}

variable "cors_allowed_origins" {
  description = "CORS Allowed origins"
}

