include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = "${get_parent_terragrunt_dir()}/modules//cloudrun"
}

dependency "vpc" {
  config_path = "../vpc"
}

dependency "database" {
  config_path = "../database"
}

dependency "dns" {
  config_path = "../dns"
}

dependency "registry" {
  config_path = "../registry"
}

inputs = {
  service_name = "public-detective-web"
  image        = "${dependency.registry.outputs.repository_url}/pd-cli:v0.1.5"

  vpc_network_id = dependency.vpc.outputs.network_id
  vpc_subnet_id  = dependency.vpc.outputs.subnet_id

  db_instance_name            = dependency.database.outputs.instance_name
  db_instance_connection_name = dependency.database.outputs.instance_connection_name

  domain_name           = "detetive-publico.com"
  dns_managed_zone_name = "detetive-publico-com"

  service_account_email = dependency.database.outputs.data_writer_email
}
