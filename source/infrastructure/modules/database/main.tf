terraform {
  required_version = ">= 1.5.7"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0"
    }
    postgresql = {
      source  = "cyrilgdn/postgresql"
      version = "~> 1.21"
    }
    random = {
      source  = "hashicorp/random"
      version = ">= 3.0"
    }
  }
}

#tfsec:ignore:google-sql-no-public-access
#tfsec:ignore:AVD-GCP-0015
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

    database_flags {
      name  = "log_temp_files"
      value = "0"
    }

    database_flags {
      name  = "log_lock_waits"
      value = "on"
    }

    database_flags {
      name  = "log_disconnections"
      value = "on"
    }

    database_flags {
      name  = "log_checkpoints"
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

# --- "Schema Admin" (Who creates tables) ---
resource "google_service_account" "schema_admin" {
  account_id   = "db-schema-admin"
  display_name = "DB Schema Admin"
}

# --- "Data Writer" (Who inserts data) ---
resource "google_service_account" "data_writer" {
  account_id   = "db-data-writer"
  display_name = "DB Data Writer"
}

# Allow db_admin_email to impersonate Schema Admin
resource "google_service_account_iam_member" "schema_admin_impersonation" {
  service_account_id = google_service_account.schema_admin.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "user:${var.db_admin_email}"
}

# Allow db_admin_email to impersonate Data Writer
resource "google_service_account_iam_member" "data_writer_impersonation" {
  service_account_id = google_service_account.data_writer.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "user:${var.db_admin_email}"
}

# Permission to LOGIN to the instance (GCP Level)
resource "google_project_iam_member" "sql_login_admin" {
  project = var.project_id
  role    = "roles/cloudsql.instanceUser"
  member  = "serviceAccount:${google_service_account.schema_admin.email}"
}

resource "google_project_iam_member" "schema_admin_client_role" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.schema_admin.email}"
}

resource "google_project_iam_member" "sql_login_writer" {
  project = var.project_id
  role    = "roles/cloudsql.instanceUser"
  member  = "serviceAccount:${google_service_account.data_writer.email}"
}

resource "google_project_iam_member" "sql_client_writer" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.data_writer.email}"
}

resource "google_sql_user" "iam_users" {
  for_each = toset([
    google_service_account.schema_admin.email,
    google_service_account.data_writer.email
  ])

  name     = trimsuffix(each.key, ".gserviceaccount.com")
  instance = google_sql_database_instance.main.name
  type     = "CLOUD_IAM_SERVICE_ACCOUNT"
}

# --- Secret Management for Postgres Password ---
resource "random_password" "postgres_password" {
  length           = 16
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

resource "google_secret_manager_secret" "postgres_password" {
  project   = var.project_id
  secret_id = "postgres-password"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "postgres_password" {
  secret      = google_secret_manager_secret.postgres_password.id
  secret_data = random_password.postgres_password.result
}

# --- Built-in Postgres User (Superuser) ---
resource "google_sql_user" "postgres" {
  project  = var.project_id
  instance = google_sql_database_instance.main.name
  name     = "postgres"
  password = random_password.postgres_password.result
}

# --- PostgreSQL Configuration ---

# 3. Configure Postgres provider to use Runner's IAM token via Local Proxy
provider "postgresql" {
  host      = "127.0.0.1"
  port      = 5433
  database  = "postgres" # Connect to default DB first
  username  = "postgres"
  password  = random_password.postgres_password.result
  sslmode   = "disable"
  superuser = false
}

# 1. Ensure Admin can USAGE and CREATE in public schema
resource "postgresql_grant" "admin_schema_perms" {
  database    = google_sql_database.app_db.name
  role        = trimsuffix(google_service_account.schema_admin.email, ".gserviceaccount.com")
  schema      = "public"
  object_type = "schema"
  privileges  = ["USAGE", "CREATE"]

  depends_on = [google_sql_user.iam_users]
}

# 2. USAGE permission on schema (to be able to "enter" the room)
resource "postgresql_grant" "writer_schema_usage" {
  database    = google_sql_database.app_db.name
  role        = trimsuffix(google_service_account.data_writer.email, ".gserviceaccount.com")
  schema      = "public"
  object_type = "schema"
  privileges  = ["USAGE"]

  depends_on = [google_sql_user.iam_users]
}

# 3. Permission on ALREADY EXISTING tables (if any)
resource "postgresql_grant" "writer_table_perms" {
  database    = google_sql_database.app_db.name
  role        = trimsuffix(google_service_account.data_writer.email, ".gserviceaccount.com")
  schema      = "public"
  object_type = "table"
  privileges  = ["SELECT", "INSERT", "UPDATE", "DELETE"]

  depends_on = [google_sql_user.iam_users]
}

resource "postgresql_grant" "writer_sequence_perms" {
  database    = google_sql_database.app_db.name
  role        = trimsuffix(google_service_account.data_writer.email, ".gserviceaccount.com")
  schema      = "public"
  object_type = "sequence"
  privileges  = ["USAGE", "SELECT"]

  depends_on = [google_sql_user.iam_users]
}

# 4. CRUCIAL: Default Privileges
# Tells the database: "Every time the schema_admin creates a table,
# automatically give permission to the data_writer"
resource "postgresql_default_privileges" "future_tables" {
  database    = google_sql_database.app_db.name
  role        = trimsuffix(google_service_account.data_writer.email, ".gserviceaccount.com")
  owner       = trimsuffix(google_service_account.schema_admin.email, ".gserviceaccount.com") # Who creates the tables
  schema      = "public"
  object_type = "table"
  privileges  = ["SELECT", "INSERT", "UPDATE", "DELETE"]

  depends_on = [google_sql_user.iam_users]
}

resource "postgresql_extension" "uuid_ossp" {
  name     = "uuid-ossp"
  database = google_sql_database.app_db.name
}
