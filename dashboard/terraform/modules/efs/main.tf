resource "aws_efs_file_system" "my_efs" {
  creation_token   = "${var.project}-${var.env}-efs"
  encrypted        = var.efs_encrypted
  performance_mode = var.efs_performance_mode
  tags = {
    Name = "${var.project}-${var.env}-efs"
  }
}

resource "aws_efs_mount_target" "my_efs_mount_targets" {
  for_each          = toset(var.subnet_ids)
  file_system_id    = aws_efs_file_system.my_efs.id
  subnet_id         = each.value
  security_groups   = [aws_security_group.efs_sg.id]
}

resource "aws_efs_access_point" "my_efs_access_point" {
  file_system_id = aws_efs_file_system.my_efs.id

  posix_user {
    gid = var.access_point_gid
    uid = var.access_point_uid
  }

  root_directory {
    path = var.efs_path
    creation_info {
      owner_gid   = var.owner_gid
      owner_uid   = var.owner_uid
      permissions = var.permissions
    }
  }
}
