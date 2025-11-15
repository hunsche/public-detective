# modules/scheduler/variables.tf

variable "project_id" {
  description = "The ID of the GCP project."
  type        = string
}

variable "region" {
  description = "The GCP region where the scheduler job will be created."
  type        = string
}

variable "service_account_email" {
  description = "The email of the service account to use for the scheduler job."
  type        = string
}

variable "cloud_run_service_url" {
  description = "The URL of the Cloud Run service to trigger."
  type        = string
}
