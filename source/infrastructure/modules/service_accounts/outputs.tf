# modules/service_accounts/outputs.tf

output "email" {
  description = "The email of the service account."
  value       = google_service_account.main.email
}

output "name" {
  description = "The name of the service account."
  value       = google_service_account.main.name
}
