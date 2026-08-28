variable "ecr_repositories" {
  description = "List of ECR repositories to create. The format of each repository needs to be a dict with the keys `name` and `max_images`"
  default     = []
}