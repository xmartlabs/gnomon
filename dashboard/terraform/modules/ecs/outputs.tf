output "cluster_id" {
  description = "ECS cluster id"
  value       = aws_ecs_cluster.aws-ecs-cluster.id
}

output "cluster_name" {
  description = "Name of the cluster"
  value       = aws_ecs_cluster.aws-ecs-cluster.name
}

output "aws_service_discovery_private_dns_namespace" {
  description = "DNS namespace"
  value       = aws_service_discovery_private_dns_namespace.segment.id
}

