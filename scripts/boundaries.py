"""Phase 5 guard preserving foundation controls; no paid scanner/service required."""

import ast
import hashlib
import json
import re
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANNED = {
    "redis",
    "celery",
    "kafka",
    "temporalio",
    "langchain",
    "openai",
    "anthropic",
    "supabase",
    "apollo",
    "zerobounce",
    "smartlead",
    "pipedrive",
    "n8n",
    "google",
    "googleapiclient",
    "gmail",
    "smtplib",
    "sendgrid",
    "mailgun",
}
BACKEND = {
    "fastapi",
    "uvicorn",
    "pydantic",
    "pydantic-settings",
    "sqlalchemy",
    "alembic",
    "psycopg",
    "pyjwt",
    "httpx",
    "httpx2",
    "openai",
    "anthropic",
}
FRONTEND = {"next", "react", "react-dom", "jose", "server-only"}
SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\b(?:ghp|github_pat|sk_live|sb_secret)_[A-Za-z0-9_]{20,}"),
    re.compile(r"postgres(?:ql)?(?:\+psycopg)?://[^\s:/]+:([A-Za-z0-9_-]{24,})@"),
]


def secret_findings(path: str, content: str) -> list[str]:
    findings = [
        f"{path}: credential pattern" for pattern in SECRET_PATTERNS if pattern.search(content)
    ]
    if Path(path).name.startswith(".env") and Path(path).name != ".env.example":
        findings.append(f"{path}: environment file must not be tracked")
    return findings


def import_findings(path: str, content: str) -> list[str]:
    findings = []
    tree = ast.parse(content)
    for node in ast.walk(tree):
        names = (
            [n.name for n in node.names]
            if isinstance(node, ast.Import)
            else [node.module or ""]
            if isinstance(node, ast.ImportFrom)
            else []
        )
        for name in names:
            if name.split(".")[0] in BANNED and not (
                name.split(".")[0] in {"openai", "anthropic"}
                and path == "packages/company_os/ai/sdk_providers.py"
            ):
                findings.append(f"{path}: prohibited dependency {name}")
            if "/domain/" in path and name.split(".")[0] in {
                "fastapi",
                "sqlalchemy",
                "httpx",
                "requests",
                "jwt",
            }:
                findings.append(f"{path}: domain cannot import {name}")
            if "/application/" in path and name.startswith(
                ("company_os.adapters", "company_os.ai.sdk_providers", "company_os.ai.providers")
            ):
                findings.append(f"{path}: application depends on concrete adapter")
    return findings


def phase_findings(path: str, content: str) -> list[str]:
    """Implementation-only guard; future architecture documentation remains allowed."""
    errors = []
    ai_module = path.startswith("packages/company_os/ai/")
    if not ai_module and re.search(
        r"(?:api\.(?:openai|anthropic|apollo)\.com|gpt-[0-9]|claude-[0-9]|text-embedding-|model_router|execute_prompt)",
        content,
        re.I,
    ):
        errors.append(f"{path}: Provider use outside the AI module is prohibited")
    if any(
        segment in path.lower()
        for segment in [
            "/campaigns/",
            "/providers/",
        ]
    ):
        errors.append(f"{path}: later-phase implementation module")
    if re.search(
        r"[\"']/(?:v1/)?(?:campaigns|opportunities|messages/.*/dispatch)(?:/|[\"'])",
        content,
    ):
        errors.append(f"{path}: later-phase route")
    if path.startswith("packages/company_os/adapters/") and not path.endswith(
        ("/auth.py", "/__init__.py")
    ):
        tree = ast.parse(content)
        for node in ast.walk(tree):
            names = (
                [part.name for part in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else []
            )
            if any(
                name.split(".")[0] in {"httpx", "requests", "socket", "aiohttp"}
                or name.startswith("urllib.request")
                for name in names
            ):
                errors.append(f"{path}: Phase 4 adapter must remain offline")
    return errors


def main() -> None:
    files = (
        subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT
        )
        .decode()
        .split("\0")
    )
    errors = []
    history = subprocess.run(
        ["git", "log", "--all", "-p", "--format="],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if history.returncode == 0:
        errors.extend(secret_findings("Git commit history", history.stdout))
    for name in filter(None, files):
        path = ROOT / name
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        errors.extend(secret_findings(name, content))
        if name.endswith(".py") and name.startswith(("apps/", "packages/company_os/")):
            errors.extend(import_findings(name, content))
            errors.extend(phase_findings(name, content))
        if name.startswith("apps/console/") and re.search(
            r"(?:process\.env\.(?:DATABASE_URL|MIGRATION_DATABASE_URL|WORKER_DATABASE_URL)|localStorage)",
            content,
        ):
            errors.append(f"{name}: forbidden browser/database boundary")
        if name.endswith(".sql") and not name.startswith("database/migrations/versions/"):
            errors.append(f"{name}: unversioned schema SQL")
        if name.startswith("database/migrations/versions/") and re.search(
            r"CREATE\s+TABLE\s+(?:app\.)?(?:ai_tasks|model_routes|prompt_versions|embeddings)\b",
            content,
            re.I,
        ):
            errors.append(f"{name}: Phase 6B schema is prohibited")
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    direct = {re.split(r"[\[<>=]", dep)[0].lower() for dep in pyproject["project"]["dependencies"]}
    if direct != BACKEND:
        errors.append("Backend dependency allowlist changed: requires ADR/review")
    frontend = json.loads((ROOT / "apps/console/package.json").read_text())["dependencies"]
    if set(frontend) != FRONTEND:
        errors.append("Frontend dependency allowlist changed: requires ADR/review")
    manifest = json.loads((ROOT / "database/migrations/manifest.json").read_text())
    for name, expected in manifest.items():
        actual = hashlib.sha256((ROOT / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        if actual != expected:
            errors.append(f"{name}: immutable migration changed")
    version_files = {
        p.as_posix().removeprefix(ROOT.as_posix() + "/")
        for p in (ROOT / "database/migrations/versions").glob("*")
        if p.suffix in {".py", ".sql"}
    }
    if version_files != set(manifest):
        errors.append("Migration history/manifest mismatch")
    if errors:
        raise SystemExit("\n".join(errors))
    print(
        f"Phase boundary, dependency, migration and secret checks passed ({len(files) - 1} files)"
    )


if __name__ == "__main__":
    main()
