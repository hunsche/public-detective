# modules/pubsub/main.tf

terraform {

  required_version = ">= 1.0.0"

  required_providers {

    google = {

      source  = "hashicorp/google"

      version = "~> 5.30"

    }

  }

}



resource "google_pubsub_topic" "main" {

  project = var.project_id

  name = "pd-procurements"

}



resource "google_pubsub_topic" "dlq" {

  project = var.project_id

  name = "pd-procurements-dlq"

}



resource "google_pubsub_subscription" "main" {

  project = var.project_id

  name = "pd-procurements-subscription"

  topic = google_pubsub_topic.main.name



  ack_deadline_seconds = 60



  dead_letter_policy {

    dead_letter_topic = google_pubsub_topic.dlq.id

    max_delivery_attempts = 5

  }

}
