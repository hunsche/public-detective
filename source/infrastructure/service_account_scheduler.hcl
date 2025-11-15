# environments/sandbox/service_account_scheduler.hcl

terraform {
  source = "../modules/service_accounts"
}

inputs = {
  service_account_name = "scheduler"
  roles = [
    "roles/run.invoker",
  ]
}
