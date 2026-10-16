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

# ==============================================================================
# Unified Custom VPC Network (Option B)
# Shared between Cloud Run agent and Private GKE cluster
# ==============================================================================
resource "google_compute_network" "custom_vpc" {
  name                    = "k8s-agent-prod-vpc"
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"
  project                 = var.project_id
}

# ==============================================================================
# Subnet 1: Cloud Run Direct VPC Egress Subnet
# ==============================================================================
resource "google_compute_subnetwork" "egress_subnet" {
  name                     = "k8s-agent-prod-egress-subnet"
  ip_cidr_range            = "10.10.1.0/24"
  region                   = var.region
  network                  = google_compute_network.custom_vpc.id
  private_ip_google_access = true
  project                  = var.project_id
}

# ==============================================================================
# Subnet 2: Private GKE Cluster Node & VPC-Native Alias IP Subnet
# ==============================================================================
resource "google_compute_subnetwork" "gke_subnet" {
  name                     = var.gke_subnet_name
  ip_cidr_range            = var.gke_subnet_cidr
  region                   = var.region
  network                  = google_compute_network.custom_vpc.id
  private_ip_google_access = true
  project                  = var.project_id
  description              = "Subnetwork for private GKE nodes with Private Google Access enabled"

  # Secondary IP range dedicated to GKE Pods (Alias IPs)
  secondary_ip_range {
    range_name    = var.gke_pods_cidr_name
    ip_cidr_range = var.gke_pods_cidr
  }

  # Secondary IP range dedicated to GKE Services (ClusterIPs)
  secondary_ip_range {
    range_name    = var.gke_services_cidr_name
    ip_cidr_range = var.gke_services_cidr
  }
}

# ==============================================================================
# Cloud Router for Shared VPC Outbound Egress
# ==============================================================================
resource "google_compute_router" "nat_router" {
  name    = "k8s-agent-nat-router"
  region  = var.region
  network = google_compute_network.custom_vpc.id
  project = var.project_id
}

# ==============================================================================
# Cloud NAT Gateway for Cloud Run & GKE Internet Egress
# ==============================================================================
resource "google_compute_router_nat" "nat_gateway" {
  name                               = "k8s-agent-nat"
  router                             = google_compute_router.nat_router.name
  region                             = var.region
  project                            = var.project_id
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "LIST_OF_SUBNETWORKS"

  # NAT for Cloud Run Direct VPC Egress
  subnetwork {
    name                    = google_compute_subnetwork.egress_subnet.id
    source_ip_ranges_to_nat = ["PRIMARY_IP_RANGE"]
  }

  # NAT for GKE nodes and pods
  subnetwork {
    name                    = google_compute_subnetwork.gke_subnet.id
    source_ip_ranges_to_nat = ["ALL_IP_RANGES"]
  }

  log_config {
    enable = true
    filter = "ERRORS_ONLY"
  }
}

# ==============================================================================
# Firewall Rules for Private GKE and Cloud Run Communication
# ==============================================================================

# 1. Intra-VPC communication (Cloud Run Agent <-> Nodes <-> Pods <-> Services)
resource "google_compute_firewall" "gke_allow_internal" {
  name        = "k8s-agent-gke-allow-internal"
  network     = google_compute_network.custom_vpc.name
  project     = var.project_id
  description = "Allow internal traffic between Cloud Run agent, GKE nodes, pods, and services"
  priority    = 1000
  direction   = "INGRESS"

  source_ranges = [
    google_compute_subnetwork.egress_subnet.ip_cidr_range,
    var.gke_subnet_cidr,
    var.gke_pods_cidr,
    var.gke_services_cidr,
  ]

  allow {
    protocol = "tcp"
  }
  allow {
    protocol = "udp"
  }
  allow {
    protocol = "icmp"
  }
  allow {
    protocol = "esp"
  }
  allow {
    protocol = "ah"
  }
}

# 2. Control plane (Master) to Node communication (kubelet 10250, admission webhooks 443)
resource "google_compute_firewall" "gke_allow_master" {
  name        = "k8s-agent-gke-allow-master"
  network     = google_compute_network.custom_vpc.name
  project     = var.project_id
  description = "Allow GKE control plane to communicate with nodes (kubelet, admission webhooks)"
  priority    = 1000
  direction   = "INGRESS"

  source_ranges = [
    var.gke_master_ipv4_cidr_block,
  ]

  allow {
    protocol = "tcp"
    ports    = ["443", "10250"]
  }
}

# 3. Google Cloud Health Checks (Load Balancer probes)
resource "google_compute_firewall" "gke_allow_health_checks" {
  name        = "k8s-agent-gke-allow-health-checks"
  network     = google_compute_network.custom_vpc.name
  project     = var.project_id
  description = "Allow Google Cloud Load Balancer health checks to GKE nodes"
  priority    = 1000
  direction   = "INGRESS"

  source_ranges = [
    "130.211.0.0/22",
    "35.191.0.0/16",
  ]

  allow {
    protocol = "tcp"
    ports    = ["80", "443", "10250", "10254", "30000-32767"]
  }
}

# 4. Identity-Aware Proxy (IAP) for secure SSH access
resource "google_compute_firewall" "allow_iap_ssh" {
  name        = "k8s-agent-allow-iap-ssh"
  network     = google_compute_network.custom_vpc.name
  project     = var.project_id
  description = "Allow Identity-Aware Proxy (IAP) TCP forwarding for secure SSH access without public IPs"
  priority    = 1000
  direction   = "INGRESS"

  source_ranges = [
    "35.235.240.0/20",
  ]

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}

# ==============================================================================
# Outputs
# ==============================================================================

output "vpc_network_name" {
  description = "Name of the custom VPC network"
  value       = google_compute_network.custom_vpc.name
}

output "vpc_network_id" {
  description = "ID of the custom VPC network"
  value       = google_compute_network.custom_vpc.id
}

output "egress_subnetwork_name" {
  description = "Name of the Cloud Run egress subnetwork"
  value       = google_compute_subnetwork.egress_subnet.name
}

output "egress_subnetwork_id" {
  description = "ID of the Cloud Run egress subnetwork"
  value       = google_compute_subnetwork.egress_subnet.id
}

output "gke_subnetwork_name" {
  description = "Name of the private GKE subnetwork"
  value       = google_compute_subnetwork.gke_subnet.name
}

output "gke_subnetwork_id" {
  description = "ID of the private GKE subnetwork"
  value       = google_compute_subnetwork.gke_subnet.id
}

output "gke_pods_secondary_range_name" {
  description = "Secondary IP range name for GKE pods"
  value       = var.gke_pods_cidr_name
}

output "gke_services_secondary_range_name" {
  description = "Secondary IP range name for GKE services"
  value       = var.gke_services_cidr_name
}

output "nat_router_name" {
  description = "Name of the Cloud Router"
  value       = google_compute_router.nat_router.name
}

output "nat_gateway_name" {
  description = "Name of the Cloud NAT gateway"
  value       = google_compute_router_nat.nat_gateway.name
}

output "gke_master_ipv4_cidr_block" {
  description = "Designated master control plane CIDR block"
  value       = var.gke_master_ipv4_cidr_block
}
