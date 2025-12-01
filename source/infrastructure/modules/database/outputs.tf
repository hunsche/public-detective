output "instance_name" {
  description = "The name of the database instance"
  value       = google_sql_database_instance.main.name
}

output "instance_connection_name" {
  description = "The connection name of the database instance"
  value       = google_sql_database_instance.main.connection_name
}

output "public_ip_address" {
  description = "The public IP address of the database instance"
  value       = google_sql_database_instance.main.public_ip_address
}

output "private_ip_address" {
  description = "The private IP address of the database instance"
  value       = google_sql_database_instance.main.private_ip_address
}

output "schema_admin_email" {
  description = "The email of the schema admin service account"
  value       = google_service_account.schema_admin.email
}

output "data_writer_email" {
  description = "The email of the data writer service account"
  value       = google_service_account.data_writer.email
}

output "db_admin_email" {
  description = "The email of the database admin user"
  value       = var.db_admin_email
}
