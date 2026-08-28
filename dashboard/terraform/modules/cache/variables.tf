variable "env" {
  description = "Name of the environment we are managing (staging, rc, production)"
}

variable "project" {
  description = "The name of the project"
}

variable "private_subnets" {
  description = "List of private subnets used by cache"
}

variable "parameter_group_name" {
  description = "The name of the parameter group to associate with this cache cluster."
}

variable "cache_engine_version" {
  description = "Version number of the cache engine to be used"
}

variable "cache_port" {
  description = "The port number on which each of the cache nodes will accept connections. For Memcached the default is 11211, and for Redis the default port is 6379."
}

variable "cache_node_type" {
  description = "Node Type used by the cache cluster"
}

variable "num_cache_nodes" {
  description = "Number of nodes used by the cache cluster"
}

variable "elasticache_engine" {
  description = "Name of the cache engine to be used for this cache cluster. Valid values are 'memcached' or 'redis'"
}

variable "cidr_block" {
  description = "VPC cidr block"
}

variable "vpc_id" {
  description = "Variable for VPC ID"
}
