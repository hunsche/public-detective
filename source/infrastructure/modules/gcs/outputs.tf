# modules/gcs/outputs.tf

output "bucket_name" {
  description = "The name of the GCS bucket."
  value       = google_storage_bucket.main.name
}
