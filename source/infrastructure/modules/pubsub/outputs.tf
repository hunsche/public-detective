# modules/pubsub/outputs.tf

output "topic_name" {
  description = "The name of the main Pub/Sub topic."
  value       = google_pubsub_topic.main.name
}

output "dlq_topic_name" {
  description = "The name of the dead-letter Pub/Sub topic."
  value       = google_pubsub_topic.dlq.name
}

output "subscription_name" {
  description = "The name of the Pub/Sub subscription."
  value       = google_pubsub_subscription.main.name
}
