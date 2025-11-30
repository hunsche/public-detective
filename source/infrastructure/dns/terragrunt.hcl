include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = "../modules/dns"
}

inputs = {
  zone_name  = "detetive-publico-com"
  domain     = "detetive-publico.com."
}
