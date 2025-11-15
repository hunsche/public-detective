# environments/sandbox/cloud_sql.hcl

terraform {
  source = "../modules/cloud_sql_postgres"
}

dependency "vpc" {
  config_path = "./vpc"
}

inputs = {
  network_id = dependency.vpc.outputs.network_name
}
