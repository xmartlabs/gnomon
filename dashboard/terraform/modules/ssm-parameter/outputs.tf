output "ssm_parameter_arns" {
  value = {
    for key, param in aws_ssm_parameter.params : key => param.arn
  }
}
