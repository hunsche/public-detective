variable "project_id" {
  description = "The ID of the project in which to provision resources."
  type        = string
}

variable "region" {
  description = "The region of the repository."
  type        = string
}

variable "repository_id" {
  description = "The last part of the repository name."
  type        = string
}
