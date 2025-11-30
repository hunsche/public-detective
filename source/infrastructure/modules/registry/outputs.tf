output "repository_url" {
  description = "The URL of the repository."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${var.repository_id}"
}

output "repository_id" {
  description = "The ID of the repository."
  value       = google_artifact_registry_repository.main.repository_id
}
