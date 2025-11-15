# environments/sandbox/vpc_access_connector.hcl

terraform {
  source = "../modules/vpc_access_connector"
}

dependency "vpc" {
  config_path = "../vpc"
}

inputs = {
  network_name = dependency.vpc.outputs.network_name
}
