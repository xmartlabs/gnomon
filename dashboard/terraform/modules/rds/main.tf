#create a security group for RDS Database Instance
resource "aws_security_group" "rds_sg" {
  name   = "${var.project}_${var.env}_rds_sg"
  vpc_id = var.vpc_id
  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [var.cidr_block]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

#create a RDS Database Instance
resource "aws_db_instance" "myinstance" {
  engine                  = var.engine
  identifier              = var.identifier
  allocated_storage       = var.rds_storage
  engine_version          = var.engine_version
  instance_class          = var.rds_instance_class
  db_name                 = var.db_name
  username                = jsondecode(data.aws_secretsmanager_secret_version.secret_password_rds.secret_string)["username"]
  password                = jsondecode(data.aws_secretsmanager_secret_version.secret_password_rds.secret_string)["password"]
  vpc_security_group_ids  = [aws_security_group.rds_sg.id]
  skip_final_snapshot     = true
  multi_az                = var.multi_az_enabled
  publicly_accessible     = var.rds_public
  db_subnet_group_name    = aws_db_subnet_group.subnetgroup.name
  backup_retention_period = var.backup_retention_period
  storage_type            = "gp3"

  # Enable Performance Insights
  performance_insights_enabled          = var.performance_insights_enabled
  performance_insights_retention_period = var.performance_insights_retention_period
  monitoring_role_arn                   = var.performance_insights_enabled ? aws_iam_role.rds_monitoring_role.arn : null
  monitoring_interval                   = var.performance_insights_enabled ? var.monitoring_interval : 0

  tags = {
    Name        = "${var.project}-${var.env}-rds-primary"
    Environment = var.env
    Project     = var.project
  }
}

# Create a Read Replica (optional)
resource "aws_db_instance" "read_replica" {
  count = var.enable_read_replica ? 1 : 0

  engine                 = var.engine
  identifier             = "${var.identifier}-replica"
  replicate_source_db    = aws_db_instance.myinstance.arn
  instance_class         = var.rds_instance_class
  vpc_security_group_ids = [aws_security_group.rds_sg.id]
  publicly_accessible    = var.rds_public
  skip_final_snapshot    = true
  db_subnet_group_name   = aws_db_subnet_group.subnetgroup.name
  storage_type           = "gp3"

  performance_insights_enabled          = var.performance_insights_enabled
  performance_insights_retention_period = var.performance_insights_retention_period
  monitoring_role_arn                   = var.performance_insights_enabled ? aws_iam_role.rds_monitoring_role.arn : null
  monitoring_interval                   = var.performance_insights_enabled ? var.monitoring_interval : 0

  tags = {
    Name        = "${var.project}-${var.env}-rds-replica"
    Environment = var.env
    Project     = var.project
  }
}

resource "aws_db_subnet_group" "subnetgroup" {
  name       = "${var.project}_${var.env}_subnet_group"
  subnet_ids = var.private_subnets

  tags = {
    Name        = "${var.project}_${var.env}_subnet_group"
    Project     = var.project
    Environment = var.env
  }
}


resource "aws_iam_role" "rds_monitoring_role" {
  name = "${var.project}-${var.env}-rds-monitoring-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "monitoring.rds.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "rds_monitoring_policy" {
  role       = aws_iam_role.rds_monitoring_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}
