# environments/sandbox/service_account_api.hcl

terraform {
  source = "../modules/service_accounts"
}

inputs = {
  service_account_name = "api"
  roles = [
    "roles/run.invoker",
    "roles/cloudsql.client",
    "roles/cloudsql.instanceUser",
    "roles/storage.objectAdmin",
    "roles.pubsub.publisher"
  ]
}
