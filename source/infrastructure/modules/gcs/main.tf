# modules/gcs/main.tf

terraform {

  required_version = ">= 1.0.0"

  required_providers {

    google = {

      source  = "hashicorp/google"

      version = "~> 5.30"

    }

  }

}



resource "google_storage_bucket" "main" {

  project = var.project_id

  name = "${var.project_id}-pd-procurements" # Bucket names must be globally unique

  location = var.region

  storage_class = "STANDARD"



  uniform_bucket_level_access = true



  lifecycle_rule {

    action {

      type = "Delete"

    }

    condition {

      age = 30

    }

  }



  versioning {

    enabled = true

  }



  lifecycle {

    prevent_destroy = true

  }

}
