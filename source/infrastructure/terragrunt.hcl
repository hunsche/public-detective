# terragrunt.hcl

# Configure the remote state backend to store Terraform state in a GCS bucket.
remote_state {
  backend = "gcs"
  config = {
    bucket = "your-terraform-state-bucket-name" # <-- IMPORTANT: Replace with a globally unique GCS bucket name
    prefix = "tfstate/default"                  # A single state for the single environment
  }
}

# Generate provider configuration that is shared by all modules.
generate "provider" {
  path      = "provider.tf"
  if_exists = "overwrite_terragrunt"
  contents  = <<EOF
provider "google" {
  project = "your-gcp-project-id" # <-- IMPORTANT: Replace with your GCP project ID
}
EOF
}

# These are the variables that will be passed to all modules.
inputs = {
  project_id      = "your-gcp-project-id" # <-- Replace with your GCP project ID
  region          = "us-central1"
  prevent_destroy = true # Always prevent destruction in the single environment
}
