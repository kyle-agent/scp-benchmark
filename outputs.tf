output "vpc_id" {
  value = samsungcloudplatformv2_vpc_vpc.this.id
}

output "subnet_id" {
  value = samsungcloudplatformv2_vpc_subnet.this.id
}

output "security_group_id" {
  value = samsungcloudplatformv2_security_group_security_group.this.id
}

output "keypair_name" {
  value = samsungcloudplatformv2_virtualserver_keypair.this.name
}

output "server" {
  value = samsungcloudplatformv2_virtualserver_server.this
}
