"""Create a source delivery ZIP, excluding transient interpreter caches."""

import argparse
import hashlib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT.parent / "deliverables")
    args = parser.parse_args()
    output = args.output.resolve()
    # Avoid accidentally packaging an archive into itself.
    if output == ROOT or ROOT in output.parents:
        raise ValueError("Output must be outside the source directory")
    output.mkdir(parents=True, exist_ok=True)
    target = output / "member-c-mvp-v0.1.0.zip"
    files = [p for p in sorted(ROOT.rglob("*")) if p.is_file()
             and not any(part in {"__pycache__", ".git", ".venv"} for part in p.relative_to(ROOT).parts)
             and p.suffix not in {".pyc", ".pyo", ".log"}]
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, Path(ROOT.name) / path.relative_to(ROOT))
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix(".zip.sha256").write_text(f"{digest}  {target.name}\n", encoding="ascii")
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        print(f"Archive: {target}\nFiles: {len(files)}\nSHA256: {digest}")


if __name__ == "__main__":
    main()
