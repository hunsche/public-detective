terraform {
  required_version = ">= 1.5.7"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0"
    }
  }
}

resource "google_dns_managed_zone" "default" {
  project     = var.project_id
  name        = var.zone_name
  dns_name    = var.domain
  description = "Managed by Terraform"
  visibility  = "public"

  dnssec_config {
    state = "on"
  }
}
