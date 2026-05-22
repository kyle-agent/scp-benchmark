#!/usr/bin/env python3
"""Generate a ceph/s3-tests INI config from S3_* environment variables.

usage: gen_config.py <output-conf-path>
"""
import os
import sys
from urllib.parse import urlparse


def env(name, default=""):
    v = os.environ.get(name)
    return v if v not in (None, "") else default


def truthy(value):
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def parse_endpoint(url):
    if "://" not in url:
        url = "https://" + url
    u = urlparse(url)
    is_secure = (u.scheme or "https") == "https"
    host = u.hostname or ""
    port = u.port or (443 if is_secure else 80)
    return host, port, is_secure


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: gen_config.py <output-conf-path>")
    out_path = sys.argv[1]

    endpoint = env("S3_ENDPOINT_URL")
    if not endpoint:
        sys.exit("ERROR: S3_ENDPOINT_URL is required")
    access = env("S3_ACCESS_KEY")
    secret = env("S3_SECRET_KEY")
    if not access or not secret:
        sys.exit("ERROR: S3_ACCESS_KEY and S3_SECRET_KEY are required")

    host, port, is_secure = parse_endpoint(endpoint)
    if not host:
        sys.exit(f"ERROR: could not parse a host from S3_ENDPOINT_URL={endpoint!r}")
    ssl_verify = truthy(env("S3_SSL_VERIFY", "true"))
    api_name = env("S3_REGION", "us-east-1")

    # Secondary users fall back to the primary credentials. The s3-tests
    # autouse setup/teardown lists buckets as the alt and tenant users before
    # every test, so those credentials must authenticate; reusing the primary
    # ones keeps the single-user API tests runnable. The iam* sections only
    # need to exist (configure() reads them unconditionally).
    alt_access = env("S3_ALT_ACCESS_KEY", access)
    alt_secret = env("S3_ALT_SECRET_KEY", secret)
    tenant_access = env("S3_TENANT_ACCESS_KEY", access)
    tenant_secret = env("S3_TENANT_SECRET_KEY", secret)

    conf = f"""[DEFAULT]
host = {host}
port = {port}
is_secure = {is_secure}
ssl_verify = {ssl_verify}

[fixtures]
bucket prefix = s3compat-{{random}}-
iam name prefix = s3compat-
iam path prefix = /s3compat/

[s3 main]
display_name = s3compat-main
user_id = s3compat-main
email = s3compat-main@example.com
api_name = {api_name}
access_key = {access}
secret_key = {secret}

[s3 alt]
display_name = s3compat-alt
user_id = s3compat-alt
email = s3compat-alt@example.com
access_key = {alt_access}
secret_key = {alt_secret}

[s3 tenant]
display_name = s3compat-tenant
user_id = s3compat-tenant
email = s3compat-tenant@example.com
tenant = s3compat
access_key = {tenant_access}
secret_key = {tenant_secret}

[iam]
display_name = s3compat-iam
user_id = s3compat-iam
email = s3compat-iam@example.com
access_key = {alt_access}
secret_key = {alt_secret}

[iam root]
display_name = s3compat-iam-root
user_id = s3compat-iam-root
email = s3compat-iam-root@example.com
access_key = {access}
secret_key = {secret}

[iam alt root]
display_name = s3compat-iam-alt-root
user_id = s3compat-iam-alt-root
email = s3compat-iam-alt-root@example.com
access_key = {alt_access}
secret_key = {alt_secret}
"""

    with open(out_path, "w") as f:
        f.write(conf)

    masked = (access[:4] + "...") if len(access) > 4 else "***"
    proto = "https" if is_secure else "http"
    print(f"Wrote s3-tests config: {out_path}")
    print(f"  endpoint   = {proto}://{host}:{port}")
    print(f"  ssl_verify = {ssl_verify}")
    print(f"  access_key = {masked}")
    if alt_access == access:
        print("  note       = alt/tenant reuse primary credentials "
              "(cross-user results are indicative only)")


if __name__ == "__main__":
    main()
