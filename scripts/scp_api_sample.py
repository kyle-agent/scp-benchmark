#!/usr/bin/env python3
"""
Sample request against the Samsung Cloud Platform (SCP) v2 OpenAPI.

Usage:
    export SCP_ACCESS_KEY=...        # from SCP console > IAM > my access key
    export SCP_SECRET_KEY=...
    export SCP_PROJECT_ID=...        # from SCP console > project
    # optional:
    export SCP_API_HOST=https://openapi.samsungsdscloud.com
    export SCP_LANGUAGE=en-US
    export SCP_PATH=/vpc/v1/vpcs     # path to call (default: list VPCs)

    python3 scripts/scp_api_sample.py

Auth scheme (per SCP OpenAPI guide):
    string_to_sign = method + encoded_path + timestamp_ms + access_key
                     + project_id + client_type
    signature      = base64( HMAC_SHA256(secret_key, string_to_sign) )

Required headers:
    X-Cmp-AccessKey, X-Cmp-Signature, X-Cmp-Timestamp,
    X-Cmp-ProjectId, X-Cmp-ClientType=OpenApi, X-Cmp-Language
"""

import base64
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


CLIENT_TYPE = "OpenApi"
DEFAULT_HOST = "https://openapi.samsungsdscloud.com"
DEFAULT_PATH = "/vpc/v1/vpcs"
DEFAULT_LANG = "en-US"


def sign(method, path, access_key, secret_key, project_id, timestamp_ms):
    encoded_path = urllib.parse.quote(path, safe="/?=&")
    msg = f"{method}{encoded_path}{timestamp_ms}{access_key}{project_id}{CLIENT_TYPE}"
    digest = hmac.new(
        secret_key.encode("utf-8"),
        msg.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("ascii")


def call(method, host, path, access_key, secret_key, project_id, language, body=None):
    timestamp_ms = str(int(time.time() * 1000))
    signature = sign(method, path, access_key, secret_key, project_id, timestamp_ms)

    headers = {
        "X-Cmp-AccessKey": access_key,
        "X-Cmp-Signature": signature,
        "X-Cmp-Timestamp": timestamp_ms,
        "X-Cmp-ProjectId": project_id,
        "X-Cmp-ClientType": CLIENT_TYPE,
        "X-Cmp-Language": language,
        "Accept": "application/json",
    }

    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(host + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


def main():
    try:
        access_key = os.environ["SCP_ACCESS_KEY"]
        secret_key = os.environ["SCP_SECRET_KEY"]
        project_id = os.environ["SCP_PROJECT_ID"]
    except KeyError as e:
        sys.exit(f"missing env var: {e.args[0]}")

    host = os.environ.get("SCP_API_HOST", DEFAULT_HOST).rstrip("/")
    path = os.environ.get("SCP_PATH", DEFAULT_PATH)
    language = os.environ.get("SCP_LANGUAGE", DEFAULT_LANG)

    print(f"GET {host}{path}")
    status, body = call("GET", host, path, access_key, secret_key, project_id, language)
    print(f"HTTP {status}")
    try:
        print(json.dumps(json.loads(body), indent=2, ensure_ascii=False))
    except json.JSONDecodeError:
        print(body)


if __name__ == "__main__":
    main()
