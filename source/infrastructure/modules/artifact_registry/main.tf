# modules/artifact_registry/main.tf

terraform {
  required_version = ">= 1.0.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.30"
    }
  }
}

resource "google_artifact_registry_repository" "main" {
  project       = var.project_id
  location      = var.region
  repository_id = "pd-docker-repo"
  description   = "Docker repository for the public-detective project"
  format        = "DOCKER"
}
