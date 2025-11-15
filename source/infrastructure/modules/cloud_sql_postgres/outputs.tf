# modules/cloud_sql_postgres/outputs.tf

output "instance_name" {
  description = "The name of the Cloud SQL instance."
  value       = google_sql_database_instance.main.name
}

output "instance_connection_name" {
  description = "The connection name of the Cloud SQL instance."
  value       = google_sql_database_instance.main.connection_name
}

output "db_name" {
  description = "The name of the database."
  value       = google_sql_database.database.name
}
