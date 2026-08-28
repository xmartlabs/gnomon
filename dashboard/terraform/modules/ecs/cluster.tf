resource "aws_ecs_cluster" "aws-ecs-cluster" {
  name = "${var.project}-${var.env}-cluster"
  tags = {
    Name        = "${var.project}-ecs"
    Environment = var.env
  }
  setting {
    name  = "containerInsights"
    value = var.container_insights
  }
}

resource "aws_ecs_cluster_capacity_providers" "example" {
  cluster_name = aws_ecs_cluster.aws-ecs-cluster.name

  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    weight            = 2
    capacity_provider = "FARGATE_SPOT"
  }
  default_capacity_provider_strategy {
    base              = 1
    weight            = 1
    capacity_provider = "FARGATE"
  }
}
