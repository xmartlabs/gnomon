data "aws_caller_identity" "current" {}

resource "aws_iam_role" "ecs-task-execution-role" {
  name               = "${var.project}-${var.env}-${var.service_name}-execution-task-role"
  assume_role_policy = data.aws_iam_policy_document.assume-role-policy.json
  tags = {
    Name        = "${var.project}-${var.env}-${var.service_name}-execution-task-role"
    Environment = var.env
  }
}

data "aws_iam_policy_document" "assume-role-policy" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy_attachment" "ecs-task-execution-role_policy" {
  role       = aws_iam_role.ecs-task-execution-role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role"
}

resource "aws_iam_policy_attachment" "test-attach" {
  name       = "${var.project}-${var.env}-${var.service_name}-policy-attachment"
  roles      = [aws_iam_role.ecs-task-execution-role.name]
  policy_arn = aws_iam_policy.ssm_policy.arn
}

resource "aws_iam_policy" "ssm_policy" {
  name        = "${var.project}-${var.env}-${var.service_name}-ssm-policy"
  path        = "/"
  description = "${var.project}-${var.env}-${var.service_name}-ssm-policy"

  # Terraform's "jsonencode" function converts a
  # Terraform expression result to valid JSON syntax.
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        "Effect" : "Allow",
        "Action" : [
          "ssm:GetParameters",
          "secretsmanager:GetSecretValue"
        ],
        "Resource" : [
          "arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter/*",
          "arn:aws:secretsmanager:${var.region}:${data.aws_caller_identity.current.account_id}:secret:*"
        ]
      },

    ]
  })
}

########## ECS EXEC POLICY #############

resource "aws_iam_policy_attachment" "ecs_exec" {
  name       = "${var.project}-${var.env}-${var.service_name}-exec-policy-attachment"
  roles      = [aws_iam_role.ecs-task-execution-role.name]
  policy_arn = aws_iam_policy.ecs_exec_policy.arn
}

resource "aws_iam_policy" "ecs_exec_policy" {
  name        = "${var.project}-${var.env}-${var.service_name}-exec-policy"
  path        = "/"
  description = "${var.project}-${var.env}-${var.service_name}-exec-policy"

  # Terraform's "jsonencode" function converts a
  # Terraform expression result to valid JSON syntax.
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        "Effect" : "Allow",
        "Action" : [
          "ecs:ExecuteCommand"
        ],
        "Resource" : [
          "arn:aws:ecs:${var.region}:${data.aws_caller_identity.current.account_id}:cluster/${var.cluster_name}"
        ]
      }

    ]
  })
}

resource "aws_iam_policy_attachment" "ecs_exec_ssm" {
  name       = "${var.project}-${var.env}-${var.service_name}-exec-ssm-policy-attachment"
  roles      = [aws_iam_role.ecs-task-execution-role.name]
  policy_arn = aws_iam_policy.ecs_exec_ssm_policy.arn
}

resource "aws_iam_policy" "ecs_exec_ssm_policy" {
  name        = "${var.project}-${var.env}-${var.service_name}-exec-ssm-policy"
  path        = "/"
  description = "${var.project}-${var.env}-${var.service_name}-exec-ssm-policy"

  # Terraform's "jsonencode" function converts a
  # Terraform expression result to valid JSON syntax.
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        "Effect" : "Allow",
        "Action" : [
          "ssmmessages:CreateControlChannel",
          "ssmmessages:CreateDataChannel",
          "ssmmessages:OpenControlChannel",
          "ssmmessages:OpenDataChannel"
        ],
        "Resource" : [
          "*"
        ]
      }

    ]
  })
}


## Cloudwatch configuration
resource "aws_cloudwatch_log_group" "log-group" {
  name = "${var.project}-${var.env}-${var.service_name}-logs"
  retention_in_days = var.log_group_retention_in_days

  tags = {
    Application = var.service_name
    Environment = var.env
  }
}


data "template_file" "env_vars" {
  template = file(var.var_file)
}
data "template_file" "secrets_vars" {
  template = file(var.secrets_file)
}

# Task and service definitions
resource "aws_ecs_task_definition" "aws-ecs-task" {
  family = "${var.project}-${var.env}-${var.service_name}-task"
  dynamic "volume" {
    for_each = var.include_efs_volume ? [1] : []
    content {
      name      = "${var.project}-${var.env}-${var.service_name}-efs-volume"

      efs_volume_configuration {
        file_system_id          = var.efs_file_system_id
        root_directory          = "/"
        transit_encryption      = "ENABLED"
        authorization_config {
          access_point_id = var.efs_access_point_id
          iam             = "ENABLED"
        }
      }
    }
  }

  container_definitions = <<DEFINITION
  [
    {
      "name": "${var.project}-${var.env}-${var.service_name}",
      "image": "${data.aws_ecr_repository.repository.repository_url}:${var.image_tag}",
      "entryPoint": [],
      "environment": ${data.template_file.env_vars.rendered},
      "secrets": ${data.template_file.secrets_vars.rendered},
      "essential": true,
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "${aws_cloudwatch_log_group.log-group.id}",
          "awslogs-region": "${var.region}",
          "awslogs-stream-prefix": "${var.project}-${var.env}-${var.service_name}"
        }
      },
      %{ if var.task_health_check_command != null }
      "healthCheck": {
        "command": ${jsonencode(var.task_health_check_command)},
        "interval": ${var.task_health_check_interval},
        "timeout": ${var.task_health_check_timeout},
        "retries": ${var.task_health_check_retries},
        "startPeriod": ${var.task_health_check_start_period}
      },
      %{ endif }

      "portMappings": [
        {
          "containerPort": ${var.docker_port},
          "hostPort": ${var.docker_port}
        }
      ],
      "cpu": ${var.cpu_amount},
      "memory": ${var.memory_amount},
      "networkMode": "awsvpc"
    }
  ]
  DEFINITION

  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  memory                   = var.memory_amount
  cpu                      = var.cpu_amount
  execution_role_arn       = aws_iam_role.ecs-task-execution-role.arn
  task_role_arn            = aws_iam_role.ecs-task-execution-role.arn

  tags = {
    Name        = "${var.project}-${var.env}-${var.service_name}-ecs-td"
    Environment = var.env
  }
}

data "aws_ecs_task_definition" "task-def" {
  task_definition = aws_ecs_task_definition.aws-ecs-task.family
}

resource "aws_ecs_service" "aws-ecs" {
  name                   = "${var.project}-${var.env}-${var.service_name}-ecs"
  cluster                = var.cluster_id
  task_definition        = "${aws_ecs_task_definition.aws-ecs-task.family}:${max(aws_ecs_task_definition.aws-ecs-task.revision, data.aws_ecs_task_definition.task-def.revision)}"
  scheduling_strategy    = "REPLICA"
  desired_count          = var.ecs_desired_count
  force_new_deployment   = true
  enable_execute_command = true

  capacity_provider_strategy {
    capacity_provider = var.capacity_provider
    weight            = 1
  }

  deployment_circuit_breaker {
    enable   = var.circuit_breaker_enabled
    rollback = var.rollback_enabled
  }
  network_configuration {
    subnets          = var.private_subnets
    assign_public_ip = false
    security_groups  = var.use_load_balancer ? [aws_security_group.backend-security-group.id, var.load_balancer_security_group_id] : [aws_security_group.backend-security-group.id]
  }

  dynamic "load_balancer" {
    # Create load balancer only if use_load_balancer variables is set to "true"
    for_each = var.use_load_balancer ? [1] : []
    content {
      target_group_arn = var.load_balancer_target_group
      container_name   = "${var.project}-${var.env}-${var.service_name}"
      container_port   = var.docker_port
    }
  }

  dynamic "service_registries" {
    for_each = var.use_autodiscovery ? [1] : []
    content {
      registry_arn   = aws_service_discovery_service.service-discovery[0].arn
      container_name = "${var.project}-${var.env}-${var.service_name}"
    }
  }
}

resource "aws_service_discovery_service" "service-discovery" {
  count = var.use_autodiscovery ? 1 : 0
  name  = var.discovery_name
  dns_config {
    namespace_id   = var.aws_service_discovery_private_dns_namespace
    routing_policy = "MULTIVALUE"
    dns_records {
      ttl  = 10
      type = "A"
    }
  }
  health_check_custom_config {
    failure_threshold = 5
  }
}


# Security groups
resource "aws_security_group" "backend-security-group" {
  vpc_id = var.vpc_id

  ingress {
    from_port       = 0
    to_port         = 0
    protocol        = "-1"
    security_groups = var.use_load_balancer ? [var.load_balancer_security_group_id] : []
  }

  egress {
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  tags = {
    Name        = "${var.project}-${var.env}-${var.service_name}-service-sg"
    Environment = var.env
  }
}

resource "aws_appautoscaling_target" "ecs_target_task-def" {
  max_capacity       = var.max_capacity
  min_capacity       = var.min_capacity
  resource_id        = "service/${var.cluster_name}/${aws_ecs_service.aws-ecs.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "ecs_policy_memory_service_1" {
  name               = "${var.project}-${var.env}-${var.service_name}-memory-autoscaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.ecs_target_task-def.resource_id
  scalable_dimension = aws_appautoscaling_target.ecs_target_task-def.scalable_dimension
  service_namespace  = aws_appautoscaling_target.ecs_target_task-def.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageMemoryUtilization"
    }

    target_value = var.autoscaling_ram_target
  }
}

resource "aws_appautoscaling_policy" "ecs_policy_cpu_service_1" {
  name               = "${var.project}-${var.env}-${var.service_name}-cpu-autoscaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.ecs_target_task-def.resource_id
  scalable_dimension = aws_appautoscaling_target.ecs_target_task-def.scalable_dimension
  service_namespace  = aws_appautoscaling_target.ecs_target_task-def.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }

    target_value = var.autoscaling_cpu_target
  }
}

data "aws_ecr_repository" "repository" {
  name = var.ecr_repo_name
}
