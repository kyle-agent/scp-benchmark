#!/usr/bin/env python3
"""Render s3tests.conf.template by substituting ${VAR} from the environment.

Usage: render_conf.py <template> <output>
Fails loudly if any referenced variable is unset.
"""
import os
import sys
from string import Template

if len(sys.argv) != 3:
    sys.exit("usage: render_conf.py <template> <output>")

template_path, out_path = sys.argv[1], sys.argv[2]
with open(template_path, encoding="utf-8") as fh:
    template = Template(fh.read())

try:
    rendered = template.substitute(os.environ)
except KeyError as exc:
    sys.exit(f"render_conf: missing environment variable {exc}")

with open(out_path, "w", encoding="utf-8") as fh:
    fh.write(rendered)
