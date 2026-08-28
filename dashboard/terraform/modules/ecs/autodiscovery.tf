########## SERVICE DISCOVERY ###############

resource "aws_service_discovery_private_dns_namespace" "segment" {
  name        = var.discovery_domain_name
  description = "Domain for all the services"
  vpc         = var.vpc_id

}