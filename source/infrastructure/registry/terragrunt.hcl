include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = "../modules/registry"
}

inputs = {
  repository_id = "public-detective"
}
