resource "samsungcloudplatformv2_vpc_vpc" "this" {
  name        = "${var.name_prefix}-vpc"
  cidr        = var.vpc_cidr
  description = "VPC created by terraform demo"
}

resource "samsungcloudplatformv2_vpc_subnet" "this" {
  name        = "${var.name_prefix}-subnet"
  vpc_id      = samsungcloudplatformv2_vpc_vpc.this.id
  type        = var.subnet_type
  cidr        = var.subnet_cidr
  description = "Subnet created by terraform demo"
}

resource "samsungcloudplatformv2_vpc_internet_gateway" "this" {
  vpc_id      = samsungcloudplatformv2_vpc_vpc.this.id
  type        = var.igw_type
  description = "IGW created by terraform demo"
}

resource "samsungcloudplatformv2_security_group_security_group" "this" {
  name        = "${var.name_prefix}-sg"
  description = "Security group created by terraform demo"
  loggable    = false
}

resource "samsungcloudplatformv2_security_group_security_group_rule" "ssh_in" {
  security_group_id = samsungcloudplatformv2_security_group_security_group.this.id
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 22
  port_range_max    = 22
  remote_ip_prefix  = var.allowed_ssh_cidr
  description       = "Allow SSH"
}

resource "samsungcloudplatformv2_security_group_security_group_rule" "egress_all" {
  security_group_id = samsungcloudplatformv2_security_group_security_group.this.id
  direction         = "egress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 1
  port_range_max    = 65535
  remote_ip_prefix  = "0.0.0.0/0"
  description       = "Allow all outbound TCP"
}

resource "samsungcloudplatformv2_virtualserver_keypair" "this" {
  name = var.keypair_name
}

resource "samsungcloudplatformv2_virtualserver_server" "this" {
  name           = "${var.name_prefix}-vm"
  state          = "ACTIVE"
  image_id       = var.image_id
  server_type_id = var.server_type_id
  keypair_name   = samsungcloudplatformv2_virtualserver_keypair.this.name

  boot_volume = {
    size                  = var.boot_volume_size
    type                  = var.boot_volume_type
    delete_on_termination = true
  }

  networks = {
    interface_1 = {
      subnet_id = samsungcloudplatformv2_vpc_subnet.this.id
    }
  }

  security_groups = [
    samsungcloudplatformv2_security_group_security_group.this.id,
  ]

  tags = {
    managed_by = "terraform"
    purpose    = "scp-demo"
  }

  depends_on = [
    samsungcloudplatformv2_security_group_security_group_rule.ssh_in,
    samsungcloudplatformv2_security_group_security_group_rule.egress_all,
    samsungcloudplatformv2_vpc_internet_gateway.this,
  ]
}
