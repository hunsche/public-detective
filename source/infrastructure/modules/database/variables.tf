variable "project_id" {
  description = "The ID of the project where this VPC will be created"
  type        = string
}

variable "region" {
  description = "The region where the database will be created"
  type        = string
}

variable "network_id" {
  description = "The ID of the VPC network to connect to"
  type        = string
}

variable "db_admin_email" {
  description = "The email of the database admin user"
  type        = string
}
