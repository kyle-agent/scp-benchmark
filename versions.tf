terraform {
  required_version = ">= 1.11"

  required_providers {
    samsungcloudplatformv2 = {
      source  = "SamsungSDSCloud/samsungcloudplatformv2"
      version = "3.2.0"
    }
  }
}

provider "samsungcloudplatformv2" {
  # access_key, secret_key, auth_url, default_region are read from
  # ~/.scpconf/credentials.json and ~/.scpconf/config.json, or from
  # SCP_TF_ACCESS_KEY / SCP_TF_SECRET_KEY / SCP_TF_AUTH_URL / SCP_TF_DEFAULT_REGION.
}
