# .tflint.hcl

# TFLint configuration file
config {
  # Enable module inspection to scan modules as well.
  module = true
  # Force TFLint to exit with a non-zero status code if issues are found.
  force = false
}

# Enable the GCP plugin
plugin "google" {
  enabled = true
}
