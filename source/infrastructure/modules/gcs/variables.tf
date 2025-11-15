# modules/gcs/variables.tf

variable "project_id" {
  description = "The ID of the GCP project."
  type        = string
}

variable "region" {
  description = "The GCP region where the bucket will be created."
  type        = string
}
