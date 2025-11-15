# modules/logging/main.tf

terraform {

  required_version = ">= 1.0.0"

  required_providers {

    google = {

      source  = "hashicorp/google"

      version = "~> 5.30"

    }

  }

}



resource "google_logging_project_exclusion" "health_checks" {

  project = var.project_id

  name = "exclude-cloud-run-health-checks"

  description = "Exclude noisy health checks from Cloud Run services."



  # This filter targets logs from Cloud Run that are part of the health check process.

  # It checks for a specific user agent used by Google's health checkers.

  filter = "resource.type=\"cloud_run_revision\" AND httpRequest.userAgent=\"Google-Health-Check\""

}



resource "google_logging_project_bucket_config" "default_log_bucket_retention" {

  project = var.project_id

  location = "global" # Log buckets are global

  bucket_id = "_Default"

  retention_days = 90 # Set retention to 3 months (90 days)

}
