provider "aws" {
  region = var.region
}

resource "aws_ec2_client_vpn_endpoint" "example_vpn" {
  description                   = var.description
  server_certificate_arn        = var.server_certificate_arn
  client_cidr_block             = var.vpn_cidr_block
  session_timeout_hours         = var.vpn_session_timeout_hours
  disconnect_on_session_timeout = var.vpn_disconnect_on_session_timeout

  authentication_options {
    type                       = "certificate-authentication"
    root_certificate_chain_arn = var.root_certificate_chain_arn
  }
  connection_log_options {
    enabled               = true
    cloudwatch_log_group  = aws_cloudwatch_log_group.vpn_log_group.name
    cloudwatch_log_stream = aws_cloudwatch_log_stream.vpn_log_stream.name
  }
  dns_servers        = var.dns_servers
  split_tunnel       = var.split_tunnel
  vpc_id             = var.vpc_id
  transport_protocol = var.transport_protocol
  tags = {
    Name = var.vpn_name
  }
}

resource "aws_cloudwatch_log_group" "vpn_log_group" {
  name              = var.cloudwatch_log_group
  retention_in_days = var.vpn_log_group_retention_in_days

  tags = {
    Environment = var.environment
    Application = "VPN"
  }
}

resource "aws_cloudwatch_log_stream" "vpn_log_stream" {
  log_group_name = aws_cloudwatch_log_group.vpn_log_group.name
  name           = var.cloudwatch_log_stream
}
resource "aws_ec2_client_vpn_network_association" "example_vpn" {
  client_vpn_endpoint_id = aws_ec2_client_vpn_endpoint.example_vpn.id
  subnet_id              = var.subnet_id
}

resource "aws_ec2_client_vpn_authorization_rule" "example_vpn" {
  client_vpn_endpoint_id = aws_ec2_client_vpn_endpoint.example_vpn.id
  target_network_cidr    = var.target_network_cidr
  authorize_all_groups   = true
}
