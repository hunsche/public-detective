# modules/cloud_run/variables.tf

variable "project_id" {
  description = "The ID of the GCP project."
  type        = string
}

variable "region" {
  description = "The GCP region where the service will be deployed."
  type        = string
}

variable "service_name" {
  description = "The name of the Cloud Run service."
  type        = string
}

variable "image_url" {
  description = "The URL of the Docker image to deploy."
  type        = string
}

variable "service_account_email" {
  description = "The email of the service account to use for the service."
  type        = string
}

variable "vpc_connector_id" {
  description = "The ID of the VPC Access Connector to use."
  type        = string
}

variable "env_vars" {
  description = "A map of environment variables to set in the container."
  type        = map(string)
  default     = {}
}
