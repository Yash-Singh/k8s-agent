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

resource "google_compute_network" "custom_vpc" {
  name                    = "k8s-agent-prod-vpc"
  auto_create_subnetworks = false
  project                 = var.project_id
  description             = "Custom VPC for k8s-agent production"

  depends_on = [
    google_project_service.services,
  ]
}

resource "google_compute_subnetwork" "egress_subnet" {
  name                     = "k8s-agent-prod-egress-subnet"
  ip_cidr_range            = "10.10.1.0/24"
  region                   = var.region
  network                  = google_compute_network.custom_vpc.id
  private_ip_google_access = true
  project                  = var.project_id
  description              = "Private egress subnet with Private Google Access enabled"
}

resource "google_compute_router" "nat_router" {
  name    = "k8s-agent-nat-router"
  region  = var.region
  network = google_compute_network.custom_vpc.id
  project = var.project_id
}

resource "google_compute_router_nat" "nat_gateway" {
  name                               = "k8s-agent-nat"
  router                             = google_compute_router.nat_router.name
  region                             = var.region
  project                            = var.project_id
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "LIST_OF_SUBNETWORKS"

  subnetwork {
    name                    = google_compute_subnetwork.egress_subnet.id
    source_ip_ranges_to_nat = ["PRIMARY_IP_RANGE"]
  }
}

output "vpc_network_name" {
  description = "Name of the custom VPC network"
  value       = google_compute_network.custom_vpc.name
}

output "vpc_network_id" {
  description = "ID of the custom VPC network"
  value       = google_compute_network.custom_vpc.id
}

output "egress_subnetwork_name" {
  description = "Name of the private egress subnetwork"
  value       = google_compute_subnetwork.egress_subnet.name
}

output "egress_subnetwork_id" {
  description = "ID of the private egress subnetwork"
  value       = google_compute_subnetwork.egress_subnet.id
}

output "nat_router_name" {
  description = "Name of the Cloud Router"
  value       = google_compute_router.nat_router.name
}

output "nat_gateway_name" {
  description = "Name of the Cloud NAT gateway"
  value       = google_compute_router_nat.nat_gateway.name
}
