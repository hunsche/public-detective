include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = "${get_parent_terragrunt_dir()}/modules//database"
}

dependency "vpc" {
  config_path = "../vpc"
}

inputs = {
  network_id     = dependency.vpc.outputs.network_id
  db_admin_email = "mthunsche@gmail.com"
}
