"""Conservative AST checks for the explicitly enumerated pure core.

Not a sandbox/security proof: this checks source policy and is complemented
by tests. Startup loaders and the local demo server are intentionally separate.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ("contracts.py", "teaching.py", "guard.py", "prompts.py", "reading.py", "events.py")
ALLOWED = {"dataclasses", "enum", "types", "typing", "collections", "datetime", "re", "unicodedata"}
BLOCKED_CALLS = {"open", "print", "exec", "eval", "__import__", "compile", "input"}
BLOCKED_METHODS = {"write", "write_text", "write_bytes", "put", "post", "send", "connect", "unlink", "mkdir", "now", "today"}


def violations(source: str) -> list[str]:
    errors = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in ALLOWED:
                    errors.append(f"line {node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                if node.module != "contracts":
                    errors.append(f"line {node.lineno}: relative import {node.module}")
            elif (node.module or "").split(".")[0] not in ALLOWED:
                errors.append(f"line {node.lineno}: import {node.module}")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in BLOCKED_CALLS:
                errors.append(f"line {node.lineno}: call {node.func.id}")
            if isinstance(node.func, ast.Attribute) and node.func.attr in BLOCKED_METHODS:
                errors.append(f"line {node.lineno}: call .{node.func.attr}")
    return errors


def check_tree() -> dict[str, list[str]]:
    return {name: errors for name in CORE if (errors := violations(
        (ROOT / "qiyan_c" / name).read_text(encoding="utf-8")
    ))}


if __name__ == "__main__":
    result = check_tree()
    print(result or "Pure core capability checks passed")
    raise SystemExit(bool(result))
