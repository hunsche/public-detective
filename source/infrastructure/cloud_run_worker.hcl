# infrastructure/cloud_run_worker.hcl

terraform {
  source = "./modules/cloud_run"
}

dependency "vpc_access_connector" {
  config_path = "./vpc_access_connector"
}

dependency "cloud_sql" {
  config_path = "./cloud_sql"
}

dependency "service_account_worker" {
  config_path = "./service_account_worker"
}

dependency "artifact_registry" {
  config_path = "./artifact_registry"
}

inputs = {

  service_name = "worker"

  image_url = "${dependency.artifact_registry.outputs.repository_url}/worker:latest" # Assumes image is tagged 'latest'

  service_account_email = dependency.service_account_worker.outputs.email

  vpc_connector_id = dependency.vpc_access_connector.outputs.connector_id

  env_vars = {

    USE_CLOUD_SQL_CONNECTOR = "true"

    INSTANCE_CONNECTION_NAME = dependency.cloud_sql.outputs.instance_connection_name

    DB_IAM_USER = dependency.service_account_worker.outputs.email

    DB_NAME = dependency.cloud_sql.outputs.db_name

  }

}
