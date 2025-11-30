output "network_name" {
  description = "The name of the VPC network."
  value       = google_compute_network.main.name
}

output "network_id" {
  description = "The ID of the VPC network."
  value       = google_compute_network.main.id
}

output "subnet_name" {
  description = "The name of the subnetwork."
  value       = google_compute_subnetwork.main.name
}

output "subnet_id" {
  description = "The ID of the subnetwork."
  value       = google_compute_subnetwork.main.id
}
