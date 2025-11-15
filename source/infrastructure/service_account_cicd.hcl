# environments/production/service_account_cicd.hcl

terraform {
  source = "../modules/service_accounts"
}

inputs = {
  service_account_name = "cicd-runner"
  # NOTE: The 'Editor' role is highly permissive. For enhanced security,
  # it is recommended to replace this with a custom role or a more
  # granular set of predefined roles that grant only the necessary
  # permissions for managing the defined resources.
  roles = [
    "roles/editor"
  ]
}
