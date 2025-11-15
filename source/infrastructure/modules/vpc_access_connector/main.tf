# modules/vpc_access_connector/main.tf

terraform {

  required_version = ">= 1.0.0"

  required_providers {

    google = {

      source = "hashicorp/google"

      version = "~> 5.0"

    }

  }

}



resource "google_vpc_access_connector" "main" {

  project = var.project_id

  name = "pd-vpc-connector"

  region = var.region

  network = var.network_name

  ip_cidr_range = "10.8.0.0/28"

}
