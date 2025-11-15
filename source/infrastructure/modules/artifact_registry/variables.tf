# modules/artifact_registry/variables.tf

variable "project_id" {
  description = "The ID of the GCP project."
  type        = string
}

variable "region" {
  description = "The GCP region where the repository will be created."
  type        = string
}
