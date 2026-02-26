#!/usr/bin/env python3
"""Convert pip-audit JSON output to GitLab dependency scanning report format.

Usage:
    uv run pip-audit -f json -o pip-audit-report.json --desc on
    python scripts/convert_pip_audit_to_gitlab.py pip-audit-report.json gl-dependency-scanning-report.json
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path


def _classify_id(vuln_id: str) -> str:
    """Classify a vulnerability ID into a GitLab identifier type."""
    vid = vuln_id.upper()
    if vid.startswith("CVE-"):
        return "cve"
    if vid.startswith("GHSA-"):
        return "ghsa"
    if vid.startswith("PYSEC-"):
        return "pypi"
    if vid.startswith("CWE-"):
        return "cwe"
    return "other"


def convert(input_path: str, output_path: str, manifest_file: str = "pyproject.toml") -> None:
    """Convert pip-audit JSON to GitLab dependency scanning report."""
    raw = json.loads(Path(input_path).read_text())

    now = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%S")
    vulnerabilities = []

    # pip-audit JSON is a flat array of {name, version, vulns: [...]}
    deps = raw if isinstance(raw, list) else raw.get("dependencies", raw)

    for dep in deps:
        pkg_name = dep["name"]
        pkg_version = dep["version"]
        for vuln in dep.get("vulns", []):
            vuln_id = vuln["id"]
            fix_versions = vuln.get("fix_versions", [])
            description = vuln.get("description", f"Vulnerability {vuln_id} in {pkg_name}")
            aliases = vuln.get("aliases", [])

            identifiers = [
                {
                    "type": _classify_id(vuln_id),
                    "name": vuln_id,
                    "value": vuln_id,
                },
            ]
            for alias in aliases:
                identifiers.append(
                    {
                        "type": _classify_id(alias),
                        "name": alias,
                        "value": alias,
                    },
                )

            solution = ""
            if fix_versions:
                solution = f"Upgrade {pkg_name} to {' or '.join(fix_versions)}"

            vulnerabilities.append(
                {
                    "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{vuln_id}:{pkg_name}:{pkg_version}")),
                    "name": f"{vuln_id} in {pkg_name}",
                    "description": description[:1_048_576],
                    "severity": "Unknown",
                    "solution": solution[:7000],
                    "identifiers": identifiers[:20],
                    "location": {
                        "file": manifest_file,
                        "dependency": {
                            "package": {"name": pkg_name},
                            "version": pkg_version,
                        },
                    },
                },
            )

    report = {
        "version": "15.1.4",
        "scan": {
            "analyzer": {
                "id": "pip-audit-converter",
                "name": "pip-audit to GitLab Converter",
                "version": "1.0.0",
                "vendor": {"name": "Custom"},
            },
            "scanner": {
                "id": "pip-audit",
                "name": "pip-audit",
                "version": "2.10.0",
                "vendor": {"name": "PyPA"},
            },
            "start_time": now,
            "end_time": now,
            "status": "success",
            "type": "dependency_scanning",
        },
        "vulnerabilities": vulnerabilities,
    }

    Path(output_path).write_text(json.dumps(report, indent=2))
    print(f"Wrote {len(vulnerabilities)} vulnerabilities to {output_path}")


_EXPECTED_ARGS = 3

if __name__ == "__main__":
    if len(sys.argv) < _EXPECTED_ARGS:
        print(f"Usage: {sys.argv[0]} <pip-audit.json> <gl-dependency-scanning-report.json>")
        sys.exit(1)
    convert(sys.argv[1], sys.argv[2])
