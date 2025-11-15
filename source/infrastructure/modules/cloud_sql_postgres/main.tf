# modules/cloud_sql_postgres/main.tf

terraform {

  required_version = ">= 1.0.0"

  required_providers {

    google = {

      source  = "hashicorp/google"

      version = "~> 5.30"

    }

    random = {

      source  = "hashicorp/random"

      version = "~> 3.0"

    }

  }

}



resource "random_password" "postgres_password" {

  length = 32

  special = true

  override_special = "_%@"

}



resource "google_secret_manager_secret" "postgres_password_secret" {



  project   = var.project_id



  secret_id = "pd-postgres-password"



}



resource "google_secret_manager_secret_version" "postgres_password_secret_version" {

  secret = google_secret_manager_secret.postgres_password_secret.id

  secret_data = random_password.postgres_password.result

}



resource "google_sql_database_instance" "main" {

  project = var.project_id

  name = "pd-postgres-instance"

  region = var.region

  database_version = "POSTGRES_16"



  settings {

    # Serverless V2 configuration

    edition = "ENTERPRISE_PLUS"

    tier = "db-f1-micro" # Base tier for Serverless V2

    availability_type = "ZONAL" # Serverless V2 is currently Zonal

    computer_auto_sizing = true # Enable autoscaling

    data_disk_auto_resize = true

    data_disk_auto_resize_limit = 0 # Unlimited storage scaling

    iam_database_authentication_enabled = true



    ip_configuration {

      ipv4_enabled = false # Disable public IP

      private_network = var.network_id

      require_ssl = true

    }

    backup_configuration {

      enabled = true # Always enabled for the single production environment

    }

    database_flags {

      name = "log_temp_files"

      value = "0"

    }

    database_flags {

      name = "log_connections"

      value = "on"

    }

    database_flags {

      name = "log_disconnections"

      value = "on"

    }

    database_flags {

      name = "log_lock_waits"

      value = "on"

    }

    database_flags {

      name = "log_checkpoints"

      value = "on"

    }

  }



  lifecycle {

    prevent_destroy = true

  }

}



resource "google_sql_database" "database" {

  project = var.project_id

  instance = google_sql_database_instance.main.name

  name = "public_detective"

}



resource "google_sql_user" "user" {

  project = var.project_id

  instance = google_sql_database_instance.main.name

  name = "postgres"

  password = random_password.postgres_password.result

}



# Private IP address for the SQL instance

resource "google_compute_global_address" "private_ip_address" {

  project = var.project_id

  name = "pd-postgres-private-ip"

  purpose = "VPC_PEERING"

  address_type = "INTERNAL"

  prefix_length = 16

  network = var.network_id

}



resource "google_service_networking_connection" "private_vpc_connection" {

  network = "projects/${var.project_id}/global/networks/${var.network_id}"

  service = "servicenetworking.googleapis.com"

  reserved_peering_ranges = [google_compute_global_address.private_ip_address.name]

}
