output "server_private_ip" {
  value = aws_instance.ec2-instance.private_ip
}

output "server_id" {
  value = aws_instance.ec2-instance.id
}

output "public_ip" {
  value = aws_instance.ec2-instance.public_ip
}
