terraform {
  required_version = ">= 1.5.7"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0"
    }
  }
}



resource "google_sql_user" "iam_service_account" {
  project  = var.project_id
  instance = var.db_instance_name
  name     = trimsuffix(var.service_account_email, ".gserviceaccount.com")
  type     = "CLOUD_IAM_SERVICE_ACCOUNT"
}

resource "google_cloud_run_v2_service" "main" {
  name                = var.service_name
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account = var.service_account_email

    containers {
      image = var.image
      args  = ["web", "serve", "--host", "0.0.0.0", "--port", "8080"]

      env {
        name  = "USE_CLOUD_SQL_AUTH"
        value = "True"
      }
      env {
        name  = "INSTANCE_CONNECTION_NAME"
        value = var.db_instance_connection_name
      }
      env {
        name  = "POSTGRES_USER"
        value = google_sql_user.iam_service_account.name
      }
      env {
        name  = "POSTGRES_DB"
        value = "public_detective"
      }
      env {
        name  = "ENV"
        value = "production"
      }
    }

    vpc_access {
      network_interfaces {
        network    = var.vpc_network_id
        subnetwork = var.vpc_subnet_id
      }
      egress = "ALL_TRAFFIC"
    }
  }

  depends_on = [google_sql_user.iam_service_account]
}

resource "google_cloud_run_service_iam_member" "public_access" {
  location = google_cloud_run_v2_service.main.location
  service  = google_cloud_run_v2_service.main.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_domain_mapping" "default" {
  location = var.region
  name     = var.domain_name

  metadata {
    namespace = var.project_id
  }

  spec {
    route_name = google_cloud_run_v2_service.main.name
  }
}

resource "google_dns_record_set" "a_records" {
  name         = "${var.domain_name}."
  managed_zone = var.dns_managed_zone_name
  type         = "A"
  ttl          = 300
  rrdatas      = [for r in google_cloud_run_domain_mapping.default.status[0].resource_records : r.rrdata if r.type == "A"]
}

resource "google_dns_record_set" "aaaa_records" {
  name         = "${var.domain_name}."
  managed_zone = var.dns_managed_zone_name
  type         = "AAAA"
  ttl          = 300
  rrdatas      = [for r in google_cloud_run_domain_mapping.default.status[0].resource_records : r.rrdata if r.type == "AAAA"]
}
resource "google_cloud_run_domain_mapping" "www" {
  location = var.region
  name     = "www.${var.domain_name}"

  metadata {
    namespace = var.project_id
  }

  spec {
    route_name = google_cloud_run_v2_service.main.name
  }
}

resource "google_dns_record_set" "www_cname" {
  name         = "www.${var.domain_name}."
  managed_zone = var.dns_managed_zone_name
  type         = "CNAME"
  ttl          = 300
  rrdatas      = ["ghs.googlehosted.com."]
}
