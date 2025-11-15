# modules/vpc_access_connector/variables.tf

variable "project_id" {
  description = "The ID of the GCP project."
  type        = string
}

variable "region" {
  description = "The GCP region where resources will be created."
  type        = string
}

variable "network_name" {
  description = "The name of the VPC network to connect to."
  type        = string
}
