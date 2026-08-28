output "vpn_client_endpoint_id" {
  description = "The ID of the VPN client endpoint."
  value       = aws_ec2_client_vpn_endpoint.wesper_vpn.id
}

output "vpn_client_endpoint_arn" {
  description = "The ARN of the VPN client endpoint."
  value       = aws_ec2_client_vpn_endpoint.wesper_vpn.arn
}
