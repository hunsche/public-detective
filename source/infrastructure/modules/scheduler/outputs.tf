# modules/scheduler/outputs.tf

output "job_name" {
  description = "The name of the Cloud Scheduler job."
  value       = google_cloud_scheduler_job.main.name
}
