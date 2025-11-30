output "repository_url" {
  description = "The URL of the repository."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${var.repository_id}"
}

output "repository_id" {
  description = "The ID of the repository."
  value       = google_artifact_registry_repository.main.repository_id
}

output "workload_identity_provider" {
  description = "The Workload Identity Provider resource name."
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "service_account_email" {
  description = "The Service Account email."
  value       = google_service_account.github_actions.email
}
