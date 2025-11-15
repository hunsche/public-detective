# environments/sandbox/service_account_worker.hcl

terraform {
  source = "../modules/service_accounts"
}

inputs = {
  service_account_name = "worker"
  roles = [
    "roles/run.invoker",
    "roles/cloudsql.client",
    "roles/cloudsql.instanceUser",
    "roles/storage.objectAdmin",
    "roles/pubsub.subscriber"
  ]
}
