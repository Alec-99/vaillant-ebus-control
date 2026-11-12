#!/usr/bin/env python3
"""Fail-closed privacy policy for a curated PUBLIC release tree.

Run before ANY public git push, even for documentation-only updates.
Use independently alongside a professional secrets scanner (Gitleaks).
No private source/captures are needed to execute this checker.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "scripts/public_manifest.txt"
IGNORED = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".venv", "dist"}
PLACEHOLDER = re.compile(r"(?i)^(?:\*+|REDACTED|EXAMPLE|CHANGE_ME|DUMMY|TEST[-_a-z0-9]*|\$\{[^}]+\}|\{[^}]+\})$")
FORBIDDEN_CONTENT = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\b(?:github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{25,})\b"),
    "cloud/API key": re.compile(r"\b(?:sk-(?:proj-)?[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,})\b"),
    "JWT": re.compile(r"\beyJ[A-Za-z0-9_-]{18,}\.eyJ[A-Za-z0-9_-]{18,}\.[A-Za-z0-9_-]{12,}\b"),
    "URL credential": re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@[^/\s\"'<>]+"),
    "private residential LAN address": re.compile(r"\b(?:192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b"),
    "private hostname": re.compile(r"(?i)\b[a-z0-9-]+\.(?:lan|local|internal)\b"),
    "MAC address": re.compile(r"(?i)\b(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}\b"),
    "raw capture container id": re.compile(r"(?i)\b197a62d9\b"),
    "household URL": re.compile(r"(?i)\bcosyhub\.eu\b"),
}
# Supervisor ingress proxy is a platform implementation detail, not a home LAN IP.
KNOWN_PLATFORM_ADDRESS = "172.30.32.2"
PRIVATE_REF = re.compile("vaillant-ebus-" + "private", re.I)
SECRET_CLI = re.compile(r"(?i)--(?:mqttuser|mqttpass|password|token)=(\S+)")
ASSIGNMENT = re.compile(r"(?i)\b(?:api[_-]?key|password|passwd|passphrase|secret|access[_-]?token)\s*[:=]\s*[\"']([^\"'\n]{7,})[\"']")


def expected_paths(root: Path) -> set[str]:
    path = root / MANIFEST
    if not path.is_file():
        raise ValueError("No public release manifest")
    items = [line.strip() for line in path.read_text(encoding="utf8").splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    if len(items) != len(set(items)):
        raise ValueError("Duplicate paths in release manifest")
    if MANIFEST not in items:
        raise ValueError("Manifest must list itself")
    for item in items:
        if item.startswith("/") or ".." in Path(item).parts or "\\" in item:
            raise ValueError("Unsafe manifest path")
        if item.startswith(("captures/", "data/", "public_release/", "private/", "memory/")):
            raise ValueError("Private path in public manifest")
        if any(part.startswith(".env") for part in Path(item).parts):
            raise ValueError("Credential file in public manifest")
    return set(items)


def audit(root: Path) -> list[str]:
    problems = []
    if not root.is_dir():
        return ["Release root does not exist"]
    try:
        expected = expected_paths(root)
    except (OSError, UnicodeError, ValueError) as exc:
        return [str(exc)]
    found = set()
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        if any(part in IGNORED for part in rel.parts):
            continue
        if path.is_symlink():
            problems.append(f"Unexpected symlink: {rel}")
            continue
        if not path.is_file():
            continue
        name = rel.as_posix()
        found.add(name)
        if name not in expected:
            problems.append(f"Unexpected public file: {name}")
            continue
        if path.stat().st_size > 250_000:
            problems.append(f"File too large for review: {name}")
            continue
        try:
            text = path.read_text(encoding="utf8")
        except (OSError, UnicodeError):
            problems.append(f"Binary or unreadable file: {name}")
            continue
        if "\x00" in text:
            problems.append(f"Binary content: {name}")
            continue
        if PRIVATE_REF.search(text) and name != "scripts/check_public_release.py":
            problems.append(f"Private repository name disclosed: {name}")
        for label, regex in FORBIDDEN_CONTENT.items():
            for match in regex.finditer(text):
                if label == "private residential LAN address" and match.group() == KNOWN_PLATFORM_ADDRESS:
                    continue
                # This checker contains its own detection strings, not secrets.
                if name == "scripts/check_public_release.py":
                    continue
                line = text.count("\n", 0, match.start()) + 1
                problems.append(f"{name}:{line}: {label}")
                if len(problems) >= 80:
                    return problems
        if name != "scripts/check_public_release.py":
            for match in SECRET_CLI.finditer(text):
                raw = match.group(1).rstrip("\"'),;")
                if not PLACEHOLDER.fullmatch(raw):
                    line = text.count("\n", 0, match.start()) + 1
                    problems.append(f"{name}:{line}: embedded command-line credential")
            for match in ASSIGNMENT.finditer(text):
                if not PLACEHOLDER.fullmatch(match.group(1)):
                    line = text.count("\n", 0, match.start()) + 1
                    problems.append(f"{name}:{line}: possible hardcoded credential")
    missing = expected - found
    for name in sorted(missing):
        problems.append(f"Manifest file missing: {name}")
    return problems


def main():
    p = argparse.ArgumentParser(description="Audit a curated release tree before public git push")
    p.add_argument("--root", type=Path, default=ROOT)
    args = p.parse_args()
    failures = audit(args.root.resolve())
    if failures:
        for failure in failures:
            print("PUBLIC RELEASE BLOCKED:", failure, file=sys.stderr)
        print(f"FAILED: {len(failures)} privacy/policy findings", file=sys.stderr)
        return 1
    print("PASS: strict file allowlist, installation details and credential patterns")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
