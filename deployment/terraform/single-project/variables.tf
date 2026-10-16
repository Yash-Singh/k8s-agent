# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

variable "project_name" {
  type        = string
  description = "Project name used as a base for resource naming"
  default     = "k8s-agent"
}

variable "project_id" {
  type        = string
  description = "Google Cloud Project ID for resource deployment."
}

variable "region" {
  type        = string
  description = "Google Cloud region for resource deployment."
  default     = "us-east1"
}

variable "telemetry_logs_filter" {
  type        = string
  description = "Log Sink filter for capturing telemetry data. Captures logs with the `traceloop.association.properties.log_type` attribute set to `tracing`."
  default     = "labels.service_name=\"k8s-agent\" labels.type=\"agent_telemetry\""
}

variable "app_sa_roles" {
  description = "List of roles to assign to the application service account"
  type        = list(string)
  default = [

    "roles/aiplatform.user",
    "roles/logging.logWriter",
    "roles/cloudtrace.agent",
    "roles/storage.admin",
    "roles/serviceusage.serviceUsageConsumer",
  ]
}

variable "gke_network_name" {
  type        = string
  description = "Name of the custom VPC network for private GKE"
  default     = "k8s-agent-gke-vpc"
}

variable "gke_subnet_name" {
  type        = string
  description = "Name of the subnetwork for GKE nodes"
  default     = "k8s-agent-gke-subnet"
}

variable "gke_subnet_cidr" {
  type        = string
  description = "Primary IP CIDR range for GKE nodes"
  default     = "10.20.0.0/20"
}

variable "gke_pods_cidr_name" {
  type        = string
  description = "Name of the secondary range for GKE pods"
  default     = "k8s-agent-gke-pods"
}

variable "gke_pods_cidr" {
  type        = string
  description = "Secondary IP CIDR range for GKE pods"
  default     = "10.48.0.0/14"
}

variable "gke_services_cidr_name" {
  type        = string
  description = "Name of the secondary range for GKE services"
  default     = "k8s-agent-gke-services"
}

variable "gke_services_cidr" {
  type        = string
  description = "Secondary IP CIDR range for GKE services"
  default     = "10.52.0.0/20"
}

variable "gke_master_ipv4_cidr_block" {
  type        = string
  description = "Master control plane IPv4 CIDR range for private GKE cluster"
  default     = "172.16.0.0/28"
}
