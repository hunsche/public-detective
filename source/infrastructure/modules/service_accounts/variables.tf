# modules/service_accounts/variables.tf

variable "project_id" {
  description = "The ID of the GCP project."
  type        = string
}

variable "service_account_name" {
  description = "The name of the service account to create."
  type        = string
}

variable "roles" {
  description = "A list of roles to assign to the service account."
  type        = list(string)
  default     = []
}
