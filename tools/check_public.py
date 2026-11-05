"""Check tracked source for common credentials and private runtime files."""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "provider-token": re.compile(rb"\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{20,}|AIza[A-Za-z0-9_-]{30,}|AKIA[A-Z0-9]{16})"),
    "private-key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "credential-url": re.compile(rb"https?://[^\s/:]+:[^\s/@]+@"),
}

def main():
    result = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True)
    paths = [Path(p.decode("utf-8")) for p in result.stdout.split(b"\0") if p]
    if not paths:
        print("No tracked files; stage the reviewed source before checking.")
        return 1
    findings = []
    for rel in paths:
        path = ROOT / rel
        name = rel.name.lower()
        if path.is_symlink():
            findings.append((rel, 0, "symlink-needs-review"))
            continue
        if not path.is_file():
            continue
        if ((name == ".env" or name.startswith(".env.")) and not name.endswith(".example")) or name == "api.txt" or path.suffix.lower() in {".db", ".sqlite", ".sqlite3", ".pem", ".pfx", ".key", ".log"}:
            findings.append((rel, 0, "private-runtime-file"))
        raw = path.read_bytes()
        if len(raw) > 25 * 1024 * 1024:
            findings.append((rel, 0, "large-file-needs-review"))
        for kind, pattern in PATTERNS.items():
            for hit in pattern.finditer(raw):
                findings.append((rel, raw.count(b"\n", 0, hit.start()) + 1, kind))
    for path, line, kind in findings:
        print(f"{path.as_posix()}:{line}: {kind}")
    print(f"Checked {len(paths)} tracked files; findings={len(findings)}")
    return bool(findings)

if __name__ == "__main__":
    sys.exit(main())
