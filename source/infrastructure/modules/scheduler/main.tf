terraform {
  required_version = ">= 1.0.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

resource "google_cloud_scheduler_job" "main" {
  project   = var.project_id
  name      = "pd-pre-analyze-job"
  region    = var.region
  schedule  = "0 0 * * *" # Daily at midnight
  time_zone = "UTC"

  http_target {
    uri         = var.cloud_run_service_url
    http_method = "POST"
    body        = base64encode("{}") # Empty JSON body

    oidc_token {
      service_account_email = var.service_account_email
    }
  }

  # This is a workaround to get the actual Cloud Run service URL
  # We will update this with the correct URL once the Cloud Run service is created
  # using a data source or by passing the URL as a variable.
  # For now, we are just creating the scheduler job.
  # The correct way to do this is to use the output of the cloud_run module
  # as an input to this module.
  # We will do this in the environment's terragrunt.hcl file.
  #
  # The following is a placeholder and will cause an error if not updated.
  # We will fix this later.
  #
  # http_target {
  #   uri = var.cloud_run_service_url
  #   ...
  # }
}
