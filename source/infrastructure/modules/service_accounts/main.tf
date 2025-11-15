# modules/service_accounts/main.tf

terraform {
  required_version = ">= 1.0.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

resource "google_service_account" "main" {
  project      = var.project_id
  account_id   = "pd-${var.service_account_name}"
  display_name = "Service Account for pd-${var.service_account_name}"
}

resource "google_project_iam_member" "main" {
  count   = length(var.roles)
  project = var.project_id
  role    = var.roles[count.index]
  member  = "serviceAccount:${google_service_account.main.email}"
}
