# Module: network

Builds a private-first VPC for EKS:

- Multi-AZ public/private/intra subnets
- NAT egress (single NAT by default for pilot cost efficiency)
- DNS support for private service discovery

Outputs are consumed by the `eks` module.
