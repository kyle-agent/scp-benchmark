variable "name_prefix" {
  type        = string
  description = "Prefix used for all resource names."
  default     = "tf-scp-demo"
}

variable "vpc_cidr" {
  type    = string
  default = "10.10.0.0/16"
}

variable "subnet_cidr" {
  type    = string
  default = "10.10.1.0/24"
}

variable "subnet_type" {
  type        = string
  description = "Subnet type. Typical values: GENERAL, LOCAL, VPC_ENDPOINT."
  default     = "GENERAL"
}

variable "igw_type" {
  type        = string
  description = "Internet gateway type. Typical values: IGW, SHARED."
  default     = "IGW"
}

variable "allowed_ssh_cidr" {
  type        = string
  description = "CIDR allowed to SSH into the VM."
  default     = "0.0.0.0/0"
}

variable "keypair_name" {
  type    = string
  default = "tf-scp-demo-key"
}

variable "image_id" {
  type        = string
  description = "Image ID for the VM (look up via SCP console or the samsungcloudplatformv2_virtualserver_images data source)."
}

variable "server_type_id" {
  type        = string
  description = "Server type (flavor) ID, e.g. s1v1m2."
}

variable "boot_volume_size" {
  type    = number
  default = 30
}

variable "boot_volume_type" {
  type    = string
  default = "SSD"
}
