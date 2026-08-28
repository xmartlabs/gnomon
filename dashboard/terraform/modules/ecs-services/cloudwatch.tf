
resource "aws_cloudwatch_metric_alarm" "ecs_tasks_not_running" {
  alarm_name          = "${var.env}_${var.service_name}_ecs_tasks_not_running"
  alarm_description   = "Running task count is lower than desired"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 1
  metric_name         = "RunningTaskCount"
  namespace           = "AWS/ECS"
  period              = 60
  statistic           = "Average"
  threshold           = var.min_capacity
  alarm_actions       = var.sns_topic_arn != null ? [var.sns_topic_arn] : []

  dimensions = {
    ClusterName = var.cluster_name
    ServiceName = aws_ecs_service.aws-ecs.name
  }

  treat_missing_data = "breaching"
}

# CPU > 80% by default
resource "aws_cloudwatch_metric_alarm" "ecs_high_cpu" {
  alarm_name          = "${var.env}_${var.service_name}_ecs_high_cpu"
  alarm_description   = "High average CPU utilization"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "AWS/ECS"
  period              = 300
  statistic           = "Average"
  threshold           = var.cpu_alarm_threshold
  alarm_actions       = var.sns_topic_arn != null ? [var.sns_topic_arn] : []

  dimensions = {
    ClusterName = var.cluster_name
    ServiceName = aws_ecs_service.aws-ecs.name
  }

  treat_missing_data = "notBreaching"
}

# Memory > 80% by default
resource "aws_cloudwatch_metric_alarm" "ecs_high_memory" {
  alarm_name          = "${var.env}_${var.service_name}_ecs_high_memory"
  alarm_description   = "High average memory utilization"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "MemoryUtilization"
  namespace           = "AWS/ECS"
  period              = 300
  statistic           = "Average"
  threshold           = var.memory_alarm_threshold
  alarm_actions       = var.sns_topic_arn != null ? [var.sns_topic_arn] : []

  dimensions = {
    ClusterName = var.cluster_name
    ServiceName = aws_ecs_service.aws-ecs.name
  }

  treat_missing_data = "notBreaching"
}
