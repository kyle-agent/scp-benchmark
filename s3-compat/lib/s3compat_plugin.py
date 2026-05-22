"""pytest plugin that records each test's markers into the JUnit XML.

Loaded via `pytest -p s3compat_plugin`. The markers land as a per-testcase
<property name="markers"> entry, which report.py uses to bucket tests into
S3 feature categories.
"""


def pytest_collection_modifyitems(config, items):
    for item in items:
        names = sorted({m.name for m in item.iter_markers()})
        item.user_properties.append(("markers", ",".join(names)))
