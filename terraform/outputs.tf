output "get_credentials" {
  value = "gcloud container clusters get-credentials ${google_container_cluster.main.name} --region ${var.region} --project ${var.project_id}"
}

output "registry" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.shop.repository_id}"
}

# Set these three as GitHub repo *variables* (Settings -> Secrets and variables -> Actions -> Variables)
output "github_variables" {
  value = {
    GCP_PROJECT_ID   = var.project_id
    GCP_WIF_PROVIDER = google_iam_workload_identity_pool_provider.github.name
    GCP_CI_SA        = google_service_account.ci.email
  }
}
