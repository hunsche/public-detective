variable "project_id" {
  description = "The ID of the project where this VPC will be created"
  type        = string
}

variable "region" {
  description = "The region where the database will be created"
  type        = string
}

variable "service_name" {
  description = "The name of the Cloud Run service"
  type        = string
}

variable "image" {
  description = "The container image to deploy"
  type        = string
}

variable "vpc_network_id" {
  description = "The ID of the VPC network to connect to"
  type        = string
}

variable "vpc_subnet_id" {
  description = "The ID of the VPC subnet to connect to"
  type        = string
}

variable "db_instance_connection_name" {
  description = "The connection name of the Cloud SQL instance"
  type        = string
}

variable "db_instance_name" {
  description = "The name of the Cloud SQL instance"
  type        = string
}

variable "domain_name" {
  description = "The domain name to map to the Cloud Run service"
  type        = string
}

variable "dns_managed_zone_name" {
  description = "The name of the Cloud DNS managed zone"
  type        = string
}

variable "service_account_email" {
  description = "The email of the service account to run the service as"
  type        = string
}
