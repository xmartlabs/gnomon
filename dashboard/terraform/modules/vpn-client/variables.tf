variable "region" {
  description = "The AWS region to deploy resources in."
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "The environment to deploy resources in."
  type        = string
  default     = "dev"
}

variable "description" {
  description = "Description of the VPN client endpoint."
  type        = string
}

variable "server_certificate_arn" {
  description = "ARN of the server certificate for the VPN endpoint."
  type        = string
}

variable "root_certificate_chain_arn" {
  description = "ARN of the root certificate chain for the VPN endpoint."
  type        = string
}

variable "cloudwatch_log_group" {
  description = "Name of the CloudWatch log group for connection logs."
  type        = string
}

variable "cloudwatch_log_stream" {
  description = "Name of the CloudWatch log stream for connection logs."
  type        = string
}

variable "dns_servers" {
  description = "List of DNS servers for the VPN endpoint."
  type        = list(string)
  default     = []
}

variable "split_tunnel" {
  description = "Whether to enable split-tunnel for the VPN endpoint."
  type        = bool
  default     = true
}

variable "vpc_id" {
  description = "ID of the VPC to associate the VPN client endpoint with."
  type        = string
}

variable "subnet_id" {
  description = "ID of the subnet to associate the VPN client endpoint with."
  type        = string
}

variable "security_group_ids" {
  description = "List of security group IDs to associate with the VPN client endpoint."
  type        = list(string)
}

variable "transport_protocol" {
  description = "List of transport protocols to enable for the VPN client endpoint."
  type        = string
  default     = "udp"
}

variable "target_network_cidr" {
  description = "CIDR block for the VPN client endpoint."
  default     = "10.0.0.0/16"
}

variable "vpn_cidr_block" {
  description = "CIDR block for the VPN client endpoint."
  type        = string
  default     = "10.200.0.0/22"
}

variable "vpn_name" {
  description = "Name for the VPN client endpoint."
  type        = string
}

variable "vpn_session_timeout_hours" {
  description = "The maximum session duration is a trigger by which end-users are required to re-authenticate prior to establishing a VPN session. Valid values: 8 | 10 | 12 | 24"
  type        = number
  default     = 8
}

variable "vpn_disconnect_on_session_timeout" {
  description = "Indicates whether the client VPN session is disconnected after the maximum session_timeout_hours is reached"
  type        = bool
  default     = true
}

variable "vpn_log_group_retention_in_days" {
  description = "Specifies the number of days you want to retain log events in the specified log group. Possible values are: 1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1096, 1827, 2192, 2557, 2922, 3288, 3653, and 0. If you select 0, the events in the log group are always retained and never expire."
  type        = number
  default     = 30
}
