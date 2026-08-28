output "efs_access_point_id" {
  description = "The ID of the EFS Access Point"
  value       = aws_efs_access_point.my_efs_access_point.id
}

output "efs_file_system_id" {
  description = "The ID of the EFS File System"
  value       = aws_efs_file_system.my_efs.id
}
