#!/usr/bin/env python3
"""Turn a ceph/s3-tests JUnit XML result into an S3 compatibility report.

Produces a per-category compatibility matrix (Markdown) plus a machine-readable
JSON. Each test is bucketed into a feature category by name, and an outcome of
pass / fail / error / skip. The compatibility percentage for a category counts
passes over executed tests (passes + failures + errors), excluding skips.

Usage:
    report.py <junit.xml> [--out-dir DIR] [--endpoint URL]
"""
import argparse
import datetime as _dt
import json
import os
import xml.etree.ElementTree as ET

# Ordered (category, keyword) rules. First keyword found in the test name wins,
# so more specific categories must come before generic ones.
CATEGORY_RULES = [
    ("Object Lock", ("object_lock", "objectlock", "retention", "legal_hold", "legalhold", "governance", "compliance")),
    ("Encryption (SSE)", ("sse", "encrypt", "kms")),
    ("Versioning", ("versioning", "delete_marker", "version")),
    ("Multipart Upload", ("multipart", "upload_part", "mpu")),
    ("Lifecycle", ("lifecycle",)),
    ("CORS", ("cors",)),
    ("Bucket Policy", ("policy",)),
    ("ACL / Grants", ("_acl", "acl_", "grant", "canned", "ownership")),
    ("Tagging", ("tagging", "_tags", "_tag")),
    ("Website", ("website",)),
    ("Bucket Logging", ("logging",)),
    ("Notifications", ("notification", "pubsub", "topic", "sns")),
    ("POST Object", ("post_object", "_post_")),
    ("Checksum", ("checksum",)),
    ("Conditional / Range", ("range", "if_match", "if_none", "ifmatch", "ifnone", "conditional", "modified", "atomic")),
    ("Copy", ("copy",)),
    ("Listing", ("delimiter", "_list", "list_", "prefix", "marker", "truncat", "continuation", "maxkeys", "max_keys", "common_prefix")),
    ("Metadata / Headers", ("metadata", "content_type", "contenttype", "cache_control", "header", "expires", "user_data")),
    ("Object CRUD", ("object", "_obj", "getobj", "putobj", "delete", "_get", "_put", "read", "write")),
    ("Bucket Ops", ("bucket",)),
]
FALLBACK_CATEGORY = "Other"


def categorize(test_name: str) -> str:
    name = test_name.lower()
    for category, keywords in CATEGORY_RULES:
        if any(kw in name for kw in keywords):
            return category
    return FALLBACK_CATEGORY


def parse_junit(path: str):
    tree = ET.parse(path)
    root = tree.getroot()
    suites = root.iter("testsuite")
    tests = []
    for suite in suites:
        for case in suite.findall("testcase"):
            name = case.get("name", "")
            classname = case.get("classname", "")
            outcome = "pass"
            message = ""
            child = None
            for tag in ("failure", "error", "skipped"):
                found = case.find(tag)
                if found is not None:
                    child = found
                    outcome = {"failure": "fail", "error": "error", "skipped": "skip"}[tag]
                    message = (found.get("message") or "").strip()
                    if not message and found.text:
                        message = found.text.strip().splitlines()[0]
                    break
            tests.append({
                "name": name,
                "classname": classname,
                "category": categorize(name),
                "outcome": outcome,
                "time": float(case.get("time", "0") or 0),
                "message": message,
            })
    return tests


def compat_pct(passed: int, failed: int, errored: int) -> float:
    executed = passed + failed + errored
    return round(100.0 * passed / executed, 1) if executed else 0.0


def aggregate(tests):
    cats = {}
    for t in tests:
        c = cats.setdefault(t["category"], {"pass": 0, "fail": 0, "error": 0, "skip": 0, "failures": []})
        c[t["outcome"]] += 1
        if t["outcome"] in ("fail", "error"):
            c["failures"].append({"name": t["name"], "outcome": t["outcome"], "message": t["message"]})
    categories = []
    for name, c in sorted(cats.items()):
        total = c["pass"] + c["fail"] + c["error"] + c["skip"]
        categories.append({
            "category": name,
            "pass": c["pass"], "fail": c["fail"], "error": c["error"], "skip": c["skip"],
            "total": total,
            "compat_pct": compat_pct(c["pass"], c["fail"], c["error"]),
            "failures": c["failures"],
        })
    totals = {
        "pass": sum(t["outcome"] == "pass" for t in tests),
        "fail": sum(t["outcome"] == "fail" for t in tests),
        "error": sum(t["outcome"] == "error" for t in tests),
        "skip": sum(t["outcome"] == "skip" for t in tests),
        "total": len(tests),
    }
    totals["compat_pct"] = compat_pct(totals["pass"], totals["fail"], totals["error"])
    return categories, totals


def truncate(text: str, n: int = 160) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


def render_markdown(categories, totals, endpoint, generated_at) -> str:
    lines = ["# S3 Compatibility Report", ""]
    if endpoint:
        lines.append(f"- **Endpoint:** `{endpoint}`")
    lines += [
        f"- **Generated:** {generated_at}",
        f"- **Tests:** {totals['total']}  "
        f"(pass {totals['pass']}, fail {totals['fail']}, error {totals['error']}, skip {totals['skip']})",
        f"- **Overall compatibility:** **{totals['compat_pct']}%** "
        f"(passes / executed; skips excluded)",
        "",
        "> Compatibility % = pass / (pass + fail + error). A failure is not "
        "necessarily a real incompatibility — many s3-tests assume "
        "AWS- or RGW-specific behaviour. Triage failures before drawing "
        "conclusions.",
        "",
        "## Compatibility matrix",
        "",
        "| Category | Pass | Fail | Error | Skip | Total | Compat % |",
        "|----------|-----:|-----:|------:|-----:|------:|---------:|",
    ]
    for c in categories:
        lines.append(
            f"| {c['category']} | {c['pass']} | {c['fail']} | {c['error']} | "
            f"{c['skip']} | {c['total']} | {c['compat_pct']}% |"
        )
    lines.append(
        f"| **Total** | **{totals['pass']}** | **{totals['fail']}** | "
        f"**{totals['error']}** | **{totals['skip']}** | **{totals['total']}** | "
        f"**{totals['compat_pct']}%** |"
    )
    lines += ["", "## Failures & errors", ""]
    any_failures = False
    for c in categories:
        if not c["failures"]:
            continue
        any_failures = True
        lines.append(f"### {c['category']} ({len(c['failures'])})")
        lines.append("")
        lines.append("| Test | Outcome | Message |")
        lines.append("|------|---------|---------|")
        for f in c["failures"]:
            lines.append(f"| `{f['name']}` | {f['outcome']} | {truncate(f['message'])} |")
        lines.append("")
    if not any_failures:
        lines.append("_No failures or errors._")
        lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("junit", help="path to JUnit XML produced by pytest")
    ap.add_argument("--out-dir", default=".", help="directory for report.md / report.json")
    ap.add_argument("--endpoint", default="", help="endpoint URL (for the report header)")
    args = ap.parse_args()

    tests = parse_junit(args.junit)
    categories, totals = aggregate(tests)
    generated_at = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    os.makedirs(args.out_dir, exist_ok=True)
    md_path = os.path.join(args.out_dir, "report.md")
    json_path = os.path.join(args.out_dir, "report.json")

    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(render_markdown(categories, totals, args.endpoint, generated_at))
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump({
            "endpoint": args.endpoint,
            "generated_at": generated_at,
            "totals": totals,
            "categories": categories,
            "tests": tests,
        }, fh, indent=2)

    print(f"[report] {totals['total']} tests, overall {totals['compat_pct']}% compatible")
    print(f"[report] wrote {md_path}")
    print(f"[report] wrote {json_path}")


if __name__ == "__main__":
    main()
