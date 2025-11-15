# modules/vpc/main.tf

terraform {
  required_version = ">= 1.0.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

resource "google_compute_network" "main" {
  project                 = var.project_id
  name                    = "pd-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "main" {
  project       = var.project_id
  name          = "private-subnet"
  ip_cidr_range = "10.0.0.0/24"
  region        = var.region
  network       = google_compute_network.main.id

  log_config {
    aggregation_interval = "INTERVAL_10_MIN"
    flow_sampling        = 0.5
    metadata             = "INCLUDE_ALL_METADATA"
  }
}
