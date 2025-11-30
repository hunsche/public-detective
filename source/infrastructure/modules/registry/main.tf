resource "google_artifact_registry_repository" "main" {
  location      = var.region
  repository_id = var.repository_id
  description   = "Docker repository for Public Detective"
  format        = "DOCKER"

  docker_config {
    immutable_tags = true
  }
}
