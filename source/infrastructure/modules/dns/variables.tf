variable "project_id" {
  description = "The ID of the project where this VPC will be created"
  type        = string
}

variable "zone_name" {
  description = "The name of the DNS zone"
  type        = string
}

variable "domain" {
  description = "The DNS name of this managed zone, for instance \"example.com.\""
  type        = string
}
