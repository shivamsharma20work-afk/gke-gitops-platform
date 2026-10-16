variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "asia-south1"
}

variable "cluster_name" {
  type    = string
  default = "gitops"
}

variable "github_repo" {
  description = "owner/name of the repo allowed to push images"
  type        = string
  default     = "shivamsharma20work-afk/gke-gitops-platform"
}
