# vpc.tf — minimal two-AZ VPC for the cluster.
#
# Public subnets only, and nodes get public IPs. That is a deliberate cost decision:
# private node subnets need a NAT gateway to pull images and reach the EKS API, and a
# NAT gateway is ~$32/month plus data processing — more than the node group itself for
# a demo that runs a few hours at a time. Nodes are still not reachable from the
# internet: the node security group only accepts traffic from the cluster security
# group and the load balancer.
#
# If this ever holds anything real, move the node group to private subnets, add a NAT
# gateway, and keep only the load balancer in the public tier.

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true # required for EKS

  tags = {
    Name = "${local.cluster_name}-vpc"
  }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "${local.cluster_name}-igw"
  }
}

resource "aws_subnet" "public" {
  count = length(local.azs)

  vpc_id                  = aws_vpc.main.id
  availability_zone       = local.azs[count.index]
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index)
  map_public_ip_on_launch = true

  tags = {
    Name = "${local.cluster_name}-public-${local.azs[count.index]}"
    # Tells the AWS cloud controller manager this subnet may host public load
    # balancers — without it, the ingress-nginx Service stays <pending>.
    "kubernetes.io/role/elb"                      = "1"
    "kubernetes.io/cluster/${local.cluster_name}" = "shared"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = {
    Name = "${local.cluster_name}-public"
  }
}

resource "aws_route_table_association" "public" {
  count = length(aws_subnet.public)

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}
