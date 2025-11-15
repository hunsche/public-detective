# environments/sandbox/scheduler.hcl

terraform {
  source = "../modules/scheduler"
}

dependency "cloud_run_api" {
  config_path = "../cloud_run_api"
}

dependency "service_account_scheduler" {
  config_path = "../service_account_scheduler"
}

inputs = {
  cloud_run_service_name = dependency.cloud_run_api.outputs.service_name
  service_account_email  = dependency.service_account_scheduler.outputs.email
  cloud_run_service_url  = dependency.cloud_run_api.outputs.service_url
}
