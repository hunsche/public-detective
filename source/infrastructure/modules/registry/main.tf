terraform {
  required_version = ">= 1.5.7"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0"
    }
  }
}

resource "google_artifact_registry_repository" "main" {
  location      = var.region
  repository_id = var.repository_id
  description   = "Docker repository for Public Detective"
  format        = "DOCKER"

  docker_config {
    immutable_tags = true
  }
}
