output "alb" {
  description = "ECS ALB"
  value       = aws_alb.application-load-balancer.dns_name
}

output "load_balancer_target_group" {
  description = "Load balancer target group"
  value       = aws_lb_target_group.target-group.arn
}

output "load_balancer_security_group_id" {
  description = "Load balancer target group"
  value       = aws_security_group.load-balancer-security-group.id
}