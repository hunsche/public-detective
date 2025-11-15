# modules/cloud_run/main.tf

terraform {

  required_version = ">= 1.0.0"

  required_providers {

    google = {

      source  = "hashicorp/google"

      version = "~> 5.30"

    }

  }

}



resource "google_cloud_run_v2_service" "main" {

  project = var.project_id

  name = "pd-${var.service_name}"

  location = var.region



  template {

    service_account = var.service_account_email



    containers {

      image = var.image_url

      ports {

        container_port = 8080

      }



      dynamic "env" {

        for_each = var.env_vars

        content {

          name = env.key

          value = env.value

        }

      }

    }



    vpc_access {

      connector = var.vpc_connector_id

      egress = "PRIVATE_RANGES_ONLY"

    }

  }



  traffic {

    percent = 100

    type = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"

  }

}



resource "google_cloud_run_service_iam_member" "allow_unauthenticated" {

  project = var.project_id

  location = var.region

  service = google_cloud_run_v2_service.main.name

  role = "roles/run.invoker"

  member = "allUsers"

}
