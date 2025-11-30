output "name_servers" {
  description = "The name servers of the managed zone"
  value       = google_dns_managed_zone.default.name_servers
}

output "zone_id" {
  description = "The ID of the managed zone"
  value       = google_dns_managed_zone.default.id
}
