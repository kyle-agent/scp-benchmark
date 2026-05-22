#!/usr/bin/env python3
"""Render a ceph/s3-tests JUnit XML run into an S3 compatibility matrix.

usage: report.py <junit.xml> <report.md> [--endpoint URL] [--s3tests-ref REF]
"""
import argparse
import datetime
import html
import xml.etree.ElementTree as ET
from collections import defaultdict

# Ordered (label, markers, keywords). First match wins, so list the specific
# feature areas before the generic CRUD catch-alls. Markers come from the
# s3compat_plugin; keywords match against "<classname> <testname>".
CATEGORIES = [
    ("STS / AssumeRole",
     {"test_of_sts", "webidentity_test", "session_policy",
      "token_claims_trust_policy_test", "token_principal_tag_role_policy_test",
      "token_request_tag_trust_policy_test", "token_resource_tags_test",
      "token_role_tags_test", "token_tag_keys_test"},
     ["test_sts", "assume_role", "web_identity", "webidentity"]),
    ("IAM / User & Role Policy",
     {"iam_account", "iam_cross_account", "iam_role", "iam_tenant", "iam_user",
      "user_policy", "role_policy", "group", "group_policy", "abac_test"},
     ["test_iam", "user_policy", "role_policy"]),
    ("S3 Select", {"s3select"}, ["s3select", "s3_select"]),
    ("Bucket Notifications", {"sns"}, ["test_sns", "notification"]),
    ("Object Lock / Retention", {"object_lock"},
     ["object_lock", "retention", "legal_hold", "governance", "worm"]),
    ("Bucket Logging",
     {"bucket_logging", "bucket_logging_cleanup", "fails_without_logging_rollover"},
     ["logging"]),
    ("Static Website",
     {"s3website", "s3website_routing_rules", "s3website_redirect_location"},
     ["website"]),
    ("Encryption (SSE)", {"encryption", "sse_s3", "bucket_encryption"},
     ["encrypt", "_sse", "sse_", "sse-c", "kms"]),
    ("Lifecycle", {"lifecycle", "lifecycle_expiration", "lifecycle_transition"},
     ["lifecycle"]),
    ("Versioning", {"versioning", "delete_marker"},
     ["versioning", "_version", "version_id"]),
    ("Object Tagging", {"tagging"}, ["tagging", "_tag"]),
    ("Bucket Policy", {"bucket_policy"}, ["bucket_policy", "_policy"]),
    ("CORS", set(), ["cors"]),
    ("ACL / Ownership", {"object_ownership"},
     ["_acl", "acl_", "grant", "ownership", "canned", "permission"]),
    ("Multipart Upload", set(), ["multipart"]),
    ("Object Copy", {"copy"}, ["copy"]),
    ("Checksums", {"checksum"}, ["checksum", "crc32", "sha256"]),
    ("Conditional Writes", {"conditional_write"},
     ["if_match", "if_none_match", "conditional", "ifmatch"]),
    ("Append Object", {"appendobject"}, ["append"]),
    ("Storage Class", {"storage_class"}, ["storage_class", "storageclass"]),
    ("Cloud Transition", {"cloud_transition", "cloud_restore", "target_by_bucket"},
     ["cloud_transition", "cloud_restore"]),
    ("Listing (v1/v2)", {"list_objects_v2"},
     ["bucket_list", "listv2", "list_delimiter", "list_prefix", "list_marker",
      "list_maxkeys", "list_many", "fetchowner", "list_objects"]),
    ("Presigned POST Upload", set(), ["post_object", "presign", "post_obj"]),
    ("Authentication / Signature", {"auth_aws2", "auth_aws4", "auth_common"},
     ["anon", "signature", "sigv", "_auth"]),
    ("Request Headers", set(),
     ["test_headers", "header", "content_md5", "content_length",
      "content_type", "expect", "100_continue"]),
    ("Object CRUD", set(), ["object", "atomic", "ranged", "range"]),
    ("Bucket CRUD", set(), ["bucket"]),
]

ORDER = [c[0] for c in CATEGORIES] + ["Other"]

# Markers that mean "this test is known to fail on a particular backend / on
# real AWS" — a failure here is more likely a test-side assumption than a real
# SCP gap.
BACKEND_MARKERS = {
    "fails_on_aws", "fails_on_rgw", "fails_on_s3", "fails_on_dbstore",
    "fails_on_dho", "fails_on_mod_proxy_fcgi", "fails_with_subdomain",
}

# Triage buckets, most-actionable verdict first.
TRIAGE_ORDER = [
    ("environment", "Environment / config"),
    ("unsupported", "Unsupported feature"),
    ("backend", "Backend-specific test assumption"),
    ("behavioral", "Behavioral difference (review)"),
]
TRIAGE_LABELS = dict(TRIAGE_ORDER)


def triage(message, markers):
    """Classify a failure to help separate real gaps from test noise."""
    m = message.lower()
    env_signals = ("ssl", "certificate", "could not connect", "connecttimeout",
                   "connectionerror", "endpointconnectionerror", "readtimeout",
                   "signaturedoesnotmatch", "name or service not known",
                   "max retries", "timed out")
    if any(s in m for s in env_signals):
        return "environment"
    unsupported_signals = ("notimplemented", "not implemented", "501",
                           "methodnotallowed", "method not allowed", "405",
                           "unsupported", "not supported")
    if any(s in m for s in unsupported_signals):
        return "unsupported"
    if set(markers) & BACKEND_MARKERS:
        return "backend"
    return "behavioral"


def categorize(classname, name, markers):
    hay = (classname + " " + name).lower()
    mset = set(markers)
    for label, mk, kws in CATEGORIES:
        if mk and (mset & mk):
            return label
        for kw in kws:
            if kw in hay:
                return label
    return "Other"


def parse_junit(path):
    """Yield dicts: {name, classname, status, markers, message}."""
    tree = ET.parse(path)
    root = tree.getroot()
    for tc in root.iter("testcase"):
        name = tc.get("name", "")
        classname = tc.get("classname", "")
        markers = []
        for prop in tc.iter("property"):
            if prop.get("name") == "markers":
                markers = [m for m in (prop.get("value") or "").split(",") if m]
        err = tc.find("error")
        fail = tc.find("failure")
        skip = tc.find("skipped")
        if err is not None:
            status, node = "error", err
        elif fail is not None:
            status, node = "failed", fail
        elif skip is not None:
            status, node = "skipped", skip
        else:
            status, node = "passed", None
        message = ""
        if node is not None:
            message = (node.get("message") or (node.text or "")).strip()
        yield {
            "name": name,
            "classname": classname,
            "status": status,
            "markers": markers,
            "message": message,
        }


def short(msg, limit=240):
    msg = " ".join(msg.split())
    return msg[:limit] + (" ..." if len(msg) > limit else "")


def pct(passed, failed):
    denom = passed + failed
    return f"{(100.0 * passed / denom):.1f}%" if denom else "n/a"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("junit")
    ap.add_argument("report")
    ap.add_argument("--endpoint", default="(unspecified)")
    ap.add_argument("--s3tests-ref", default="unknown")
    args = ap.parse_args()

    cases = list(parse_junit(args.junit))

    # tally[label] = {passed, failed, skipped}  (error folded into failed)
    tally = defaultdict(lambda: {"passed": 0, "failed": 0, "skipped": 0})
    failures = defaultdict(list)  # label -> [(name, message, triage_key)]
    triage_counts = defaultdict(int)
    for c in cases:
        label = categorize(c["classname"], c["name"], c["markers"])
        if c["status"] in ("failed", "error"):
            tally[label]["failed"] += 1
            msg = c["message"] or c["status"]
            tkey = triage(msg, c["markers"])
            triage_counts[tkey] += 1
            failures[label].append((c["name"], msg, tkey))
        elif c["status"] == "skipped":
            tally[label]["skipped"] += 1
        else:
            tally[label]["passed"] += 1

    tot_pass = sum(t["passed"] for t in tally.values())
    tot_fail = sum(t["failed"] for t in tally.values())
    tot_skip = sum(t["skipped"] for t in tally.values())
    total = tot_pass + tot_fail + tot_skip

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = []
    lines.append("# S3 Compatibility Report")
    lines.append("")
    lines.append(f"- **Endpoint:** `{args.endpoint}`")
    lines.append(f"- **Generated:** {now}")
    lines.append(f"- **Test suite:** ceph/s3-tests @ `{args.s3tests_ref}`")
    lines.append(f"- **Total tests:** {total} "
                 f"(passed {tot_pass}, failed {tot_fail}, skipped {tot_skip})")
    lines.append(f"- **Overall compatibility:** **{pct(tot_pass, tot_fail)}** "
                 f"(passed / (passed + failed), skipped excluded)")
    lines.append("")
    lines.append("## Compatibility matrix")
    lines.append("")
    lines.append("| Category | Pass | Fail | Skip | Compatibility |")
    lines.append("|---|---:|---:|---:|---:|")
    for label in ORDER:
        if label not in tally:
            continue
        t = tally[label]
        lines.append(f"| {label} | {t['passed']} | {t['failed']} | "
                     f"{t['skipped']} | {pct(t['passed'], t['failed'])} |")
    lines.append(f"| **TOTAL** | **{tot_pass}** | **{tot_fail}** | "
                 f"**{tot_skip}** | **{pct(tot_pass, tot_fail)}** |")
    lines.append("")

    if tot_fail:
        lines.append("## Failure triage")
        lines.append("")
        lines.append("Heuristic classification of the failing tests to separate "
                     "likely real gaps from test-suite noise.")
        lines.append("")
        lines.append("| Triage | Count | Meaning |")
        lines.append("|---|---:|---|")
        meanings = {
            "environment": "TLS/connection/signature errors — fix the harness or "
                           "network, then re-run (not a real result).",
            "unsupported": "Server returned NotImplemented / 405 / not-supported — "
                           "the feature is likely absent.",
            "backend": "Test is marked fails_on_aws/rgw/etc — the assertion is "
                       "backend-specific, not necessarily a real incompatibility.",
            "behavioral": "Behavior diverged from the S3 reference — needs manual "
                          "review to confirm a true gap.",
        }
        for key, label in TRIAGE_ORDER:
            if triage_counts.get(key):
                lines.append(f"| {label} | {triage_counts[key]} | {meanings[key]} |")
        lines.append("")

    lines.append("## Notes")
    lines.append("")
    lines.append("- **Compatibility** = passed / (passed + failed). Skipped tests "
                 "are excluded from the percentage.")
    lines.append("- A **failure** means the endpoint's behavior diverged from the "
                 "S3 reference behavior asserted by ceph/s3-tests; it may indicate "
                 "an unsupported feature or a behavioral difference.")
    lines.append("- Categories are assigned heuristically from pytest markers and "
                 "test names; a few tests may land in an adjacent bucket.")
    lines.append("- If alt/tenant credentials were not configured, cross-user, "
                 "ACL, and tenant results are **indicative only** (a single "
                 "identity cannot exercise true multi-user isolation).")
    lines.append("")

    failing_labels = [l for l in ORDER if failures.get(l)]
    if failing_labels:
        lines.append("## Failure details")
        lines.append("")
        for label in failing_labels:
            items = failures[label]
            lines.append(f"<details><summary>{html.escape(label)} "
                         f"({len(items)} failing)</summary>")
            lines.append("")
            for name, msg, tkey in items:
                tag = TRIAGE_LABELS[tkey]
                lines.append(f"- `{name}` _[{tag}]_ — {html.escape(short(msg))}")
            lines.append("")
            lines.append("</details>")
            lines.append("")

    with open(args.report, "w") as f:
        f.write("\n".join(lines) + "\n")

    print(f"Overall compatibility: {pct(tot_pass, tot_fail)} "
          f"({tot_pass}/{tot_pass + tot_fail} passed, {tot_skip} skipped)")
    print(f"Report: {args.report}")


if __name__ == "__main__":
    main()
