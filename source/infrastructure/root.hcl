remote_state {
  backend = "gcs"
  config = {
    bucket = "terraform-state-${get_env("GCP_PROJECT")}"
    prefix = "tfstate/${path_relative_to_include()}"
  }
}

generate "backend" {
  path      = "backend.tf"
  if_exists = "overwrite_terragrunt"
  contents  = <<EOF
terraform {
  backend "gcs" {}
}
EOF
}

generate "provider" {
  path      = "provider.tf"
  if_exists = "overwrite_terragrunt"
  contents  = <<EOF
provider "google" {
project = "${get_env("GCP_PROJECT")}"
}
EOF
}

inputs = {
  project_id      = get_env("GCP_PROJECT")
  region          = "us-central1"
  prevent_destroy = true
}
