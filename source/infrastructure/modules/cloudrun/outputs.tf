output "service_name" {
  description = "The name of the Cloud Run service."
  value       = google_cloud_run_v2_service.main.name
}

output "service_url" {
  description = "The URL of the Cloud Run service."
  value       = google_cloud_run_v2_service.main.uri
}

output "domain_mapping_status" {
  description = "The status of the domain mapping."
  value       = google_cloud_run_domain_mapping.default.status
}
