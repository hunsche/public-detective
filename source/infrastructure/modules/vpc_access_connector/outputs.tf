# modules/vpc_access_connector/outputs.tf

output "connector_id" {
  description = "The ID of the VPC Access Connector."
  value       = google_vpc_access_connector.main.id
}
