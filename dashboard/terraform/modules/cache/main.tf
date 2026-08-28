resource "aws_elasticache_cluster" "cache" {
  cluster_id           = "${var.project}-${var.env}-cache"
  engine               = var.elasticache_engine
  node_type            = var.cache_node_type
  num_cache_nodes      = var.num_cache_nodes
  parameter_group_name = var.parameter_group_name
  engine_version       = var.cache_engine_version
  port                 = var.cache_port
  subnet_group_name    = aws_elasticache_subnet_group.subnet_group_cache.name
  security_group_ids   = ["${aws_security_group.cache_sg.id}"]
}

resource "aws_elasticache_subnet_group" "subnet_group_cache" {
  name       = "${var.project}-${var.env}-cache-subnet-group"
  subnet_ids = var.private_subnets

  tags = {
    Name        = "${var.project}-${var.env}-subnet-group-cache"
    Project     = var.project
    Environment = var.env
  }
}

#create a security group for the Cache
resource "aws_security_group" "cache_sg" {
  name   = "${var.project}_${var.env}_cache_sg"
  vpc_id = var.vpc_id
  ingress {
    from_port   = 6379
    to_port     = 6379
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
