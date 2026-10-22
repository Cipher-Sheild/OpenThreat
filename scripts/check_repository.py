"""Check the staged publication snapshot without reading private environment files."""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)

def main():
    names = git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z").decode().split("\0")
    errors = []
    checked = 0
    for name in filter(None, names):
        path = Path(name)
        if (path.name == ".env" or (path.name.startswith(".env.") and path.name != ".env.example")
                or any(part in {"node_modules", "model_cache", ".local-backups", "__pycache__"} for part in path.parts)
                or path.suffix.lower() in {".dump", ".sqlite", ".safetensors", ".pt", ".zip"}):
            errors.append(f"Private or generated file staged: {name}")
            continue
        data = git("show", f":{name}")
        if b"\0" in data[:8192]:
            continue
        text = data.decode("utf-8", errors="replace")
        # These patterns require plausible credentials, not environment placeholders.
        for pattern in (r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
                        r"\bAKIA[0-9A-Z]{16}\b", r"\bhf_[a-zA-Z0-9]{25,}\b",
                        r"\bgh[pousr]_[a-zA-Z0-9]{30,}\b"):
            if re.search(pattern, text):
                errors.append(f"Possible credential: {name}")
        checked += 1
    print(f"Checked {checked} staged text files. {len(errors)} issues.")
    for error in errors:
        print(error)
    return bool(errors)

if __name__ == "__main__":
    sys.exit(main())
