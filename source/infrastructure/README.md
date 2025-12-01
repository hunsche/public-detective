# Infrastructure Setup

This directory contains the Infrastructure as Code (IaC) for the project, managed with Terragrunt and Terraform.

## Prerequisites

- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install)
- [Terraform](https://www.terraform.io/downloads)
- [Terragrunt](https://terragrunt.gruntwork.io/docs/getting-started/installation/)

## Setup

1.  **Authenticate with Google Cloud:**

    ```bash
    gcloud auth application-default login
    ```

2.  **Set Environment Variables:**

    You must export your Google Cloud Project ID. This is used to dynamically configure the state bucket and provider.

    ```bash
    export GCP_PROJECT=your-project-id
    ```

3.  **Create Terraform State Bucket:**

    Before running Terragrunt, ensure the GCS bucket for remote state exists. The bucket name follows the pattern `terraform-state-<PROJECT_ID>`.

    ```bash
    # Create the bucket
    gcloud storage buckets create gs://terraform-state-$GCP_PROJECT --project=$GCP_PROJECT --location=us-central1 --uniform-bucket-level-access

    # Enable versioning (recommended for state buckets)
    gcloud storage buckets update gs://terraform-state-$GCP_PROJECT --versioning-enabled
    ```

4.  **Start Cloud SQL Proxy:**

    To run database migrations or populate data locally, you need the Cloud SQL Proxy running.

    ```bash
    # Replace <PROJECT_ID> with your actual project ID
    cloud-sql-proxy --port 5433 --auto-iam-authn <PROJECT_ID>:us-central1:postgres-01
    ```

## Usage

We use `terragrunt` to manage the infrastructure.

### Plan

To see what changes will be made:

```bash
# Run from source/infrastructure
terragrunt run --all plan
```

### Apply

To apply the changes:

```bash
# Run from source/infrastructure
terragrunt run --all apply
```

### Directory Structure

- `root.hcl`: Root Terragrunt configuration (backend, provider).
- `vpc/`: VPC module configuration.
