resource "aws_security_group" "security_group" {
  name   = "${var.project}-${var.env}-ec2-sg"
  vpc_id = var.vpc_id
  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "${var.project}-${var.env}-ec2-sg"
    Project     = var.project
    Environment = var.env
  }
}

resource "aws_instance" "ec2-instance" {
  ami                    = var.amiid
  instance_type          = var.instance_type
  subnet_id              = var.subnet_id
  vpc_security_group_ids = [aws_security_group.security_group.id]

  root_block_device {
    volume_size = var.root_disk_volume_size
  }

  key_name  = var.key_name
  user_data = templatefile(var.create_machine_script, {})

  tags = {
    Name        = "${var.project}_${var.env}-ec2"
    Project     = var.project
    Environment = var.env
  }

  iam_instance_profile = var.iam_instance_profile
}

resource "aws_eip" "eip" {
  count    = var.create_eip ? 1 : 0
  instance = aws_instance.ec2-instance.id
  domain   = "vpc"
}

