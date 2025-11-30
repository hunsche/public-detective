terraform {
  required_version = ">= 1.5.7"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0"
    }
  }
}

#tfsec:ignore:google-sql-no-public-access
resource "google_sql_database_instance" "main" {
  project             = var.project_id
  name                = "postgres-01"
  region              = var.region
  database_version    = "POSTGRES_16"
  deletion_protection = true

  settings {
    edition           = "ENTERPRISE"
    tier              = "db-f1-micro"
    availability_type = "ZONAL"
    disk_autoresize   = true
    disk_size         = 10
    disk_type         = "PD_HDD"

    ip_configuration {
      ipv4_enabled    = true
      private_network = var.network_id
      ssl_mode        = "ENCRYPTED_ONLY"
    }

    backup_configuration {
      enabled    = true
      start_time = "04:00"
    }

    database_flags {
      name  = "log_connections"
      value = "on"
    }

    database_flags {
      name  = "cloudsql.iam_authentication"
      value = "on"
    }
  }
}

resource "google_sql_database" "app_db" {
  project  = var.project_id
  instance = google_sql_database_instance.main.name
  name     = "public_detective"
}

resource "google_sql_user" "iam_admin" {
  project  = var.project_id
  instance = google_sql_database_instance.main.name
  name     = var.db_admin_email
  type     = "CLOUD_IAM_USER"
}

resource "google_project_iam_member" "user_login_role" {
  project = var.project_id
  role    = "roles/cloudsql.instanceUser"
  member  = "user:${var.db_admin_email}"
}

resource "google_project_iam_member" "user_client_role" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "user:${var.db_admin_email}"
}
