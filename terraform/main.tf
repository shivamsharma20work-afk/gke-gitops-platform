terraform {
  required_version = ">= 1.9"
  required_providers {
    google = { source = "hashicorp/google", version = "~> 6.0" }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_project_service" "apis" {
  for_each = toset([
    "container.googleapis.com",
    "artifactregistry.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "sts.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

# --- GKE Autopilot: Google manages nodes, we pay per pod request -------------

resource "google_container_cluster" "main" {
  name                = var.cluster_name
  location            = var.region
  enable_autopilot    = true
  deletion_protection = false

  release_channel {
    channel = "REGULAR"
  }

  depends_on = [google_project_service.apis]
}

# --- Artifact Registry --------------------------------------------------------

resource "google_artifact_registry_repository" "shop" {
  repository_id = "shop"
  location      = var.region
  format        = "DOCKER"

  cleanup_policies {
    id     = "keep-last-20"
    action = "KEEP"
    most_recent_versions { keep_count = 20 }
  }

  depends_on = [google_project_service.apis]
}

# GKE nodes pull images with the default compute SA
data "google_project" "this" {}

resource "google_artifact_registry_repository_iam_member" "nodes_pull" {
  location   = google_artifact_registry_repository.shop.location
  repository = google_artifact_registry_repository.shop.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${data.google_project.this.number}-compute@developer.gserviceaccount.com"
}

# --- GitHub Actions -> GCP without a JSON key (Workload Identity Federation) --

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"
  depends_on                = [google_project_service.apis]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-oidc"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }
  # Only this repo's main branch can get a token
  attribute_condition = "assertion.repository == '${var.github_repo}' && assertion.ref == 'refs/heads/main'"
}

resource "google_service_account" "ci" {
  account_id   = "gh-actions-pusher"
  display_name = "GitHub Actions image pusher"
}

# CI can push images to this one repo. It has no cluster access: Argo CD deploys, not CI.
resource "google_artifact_registry_repository_iam_member" "ci_push" {
  location   = google_artifact_registry_repository.shop.location
  repository = google_artifact_registry_repository.shop.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.ci.email}"
}

resource "google_service_account_iam_member" "ci_wif" {
  service_account_id = google_service_account.ci.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repo}"
}
