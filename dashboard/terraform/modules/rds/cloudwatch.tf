
resource "aws_cloudwatch_metric_alarm" "rds_high_cpu" {
  alarm_name          = "${var.env}_rds_high_cpu"
  alarm_description   = "CPU usage over 80%"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  alarm_actions       = var.sns_topic_arn != null ? [var.sns_topic_arn] : null

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.myinstance.identifier
  }

  treat_missing_data = "notBreaching"
}

resource "aws_cloudwatch_metric_alarm" "rds_disk_queue" {
  alarm_name          = "${var.env}_rds_disk_queue_depth"
  alarm_description   = "Disk queue depth over 64"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "DiskQueueDepth"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = var.disk_queue_depth_alarm_threshold
  alarm_actions       = var.sns_topic_arn != null ? [var.sns_topic_arn] : null

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.myinstance.identifier
  }

  treat_missing_data = "notBreaching"
}

# Free storage < 10 GB
resource "aws_cloudwatch_metric_alarm" "rds_low_storage" {
  alarm_name          = "${var.env}_rds_low_storage"
  alarm_description   = "Free storage space below 10GB"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 1
  metric_name         = "FreeStorageSpace"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = var.free_storage_alarm_threshold
  alarm_actions       = var.sns_topic_arn != null ? [var.sns_topic_arn] : null

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.myinstance.identifier
  }

  treat_missing_data = "notBreaching"
}

# Connections > 90%
resource "aws_cloudwatch_metric_alarm" "rds_high_connections" {
  alarm_name          = "${var.env}_rds_high_connections"
  alarm_description   = "High number of database connections"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "DatabaseConnections"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = var.connections_alarm_threshold
  alarm_actions       = var.sns_topic_arn != null ? [var.sns_topic_arn] : null

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.myinstance.identifier
  }

  treat_missing_data = "notBreaching"
}

# Failover or instance restart
resource "aws_cloudwatch_metric_alarm" "rds_failover" {
  alarm_name          = "${var.env}_rds_failover"
  alarm_description   = "RDS instance rebooted or failed over"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Failover"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Sum"
  threshold           = 1
  alarm_actions       = var.sns_topic_arn != null ? [var.sns_topic_arn] : null

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.myinstance.identifier
  }

  treat_missing_data = "notBreaching"
}
