terraform {
  required_version = ">= 1.5.7"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0"
    }
  }
}

resource "google_compute_network" "main" {
  project                 = var.project_id
  name                    = "main"
  auto_create_subnetworks = false
  mtu                     = 1460
}

# trivy:ignore:AVD-GCP-0029
resource "google_compute_subnetwork" "main" {
  project                  = var.project_id
  name                     = "us-central1"
  ip_cidr_range            = "10.0.0.0/20"
  region                   = var.region
  network                  = google_compute_network.main.id
  private_ip_google_access = true
}

resource "google_compute_global_address" "private_ip_alloc" {
  project       = var.project_id
  name          = "ip-range-services"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.main.id
}

resource "google_service_networking_connection" "private_vpc_connection" {
  network                 = google_compute_network.main.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_ip_alloc.name]
}
