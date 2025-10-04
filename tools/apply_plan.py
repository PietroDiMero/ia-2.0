from __future__ import annotationsfrom __future__ import annotations

"""Apply an evolver plan produced by evolver/mentor.py using evolver/builder logic.

import json

This script is intentionally minimal so it can run in CI where only the root requirementsfrom pathlib import Path

are installed. It wraps builder.py's CLI to avoid code duplication while allowing thefrom typing import Dict, Any

workflow step to call a stable path: tools/apply_plan.py

"""

import argparseROOT = Path(__file__).resolve().parents[1]

import sys

from pathlib import Path

def apply_patch(file_path: Path, patch: str) -> None:

ROOT = Path(__file__).resolve().parents[1]    if patch.startswith("PATCH:WRITE\n"):

BUILDER = ROOT / "evolver" / "builder.py"        content = patch.split("\n", 1)[1]

        file_path.parent.mkdir(parents=True, exist_ok=True)

        file_path.write_text(content, encoding="utf-8")

def main() -> int:    elif patch.startswith("PATCH:APPEND\n"):

    parser = argparse.ArgumentParser(description="Wrapper to apply evolver plan")        content = patch.split("\n", 1)[1]

    parser.add_argument("--plan", default="evolver_plan.json", help="Path to plan JSON")        file_path.parent.mkdir(parents=True, exist_ok=True)

    parser.add_argument("--dry-run", action="store_true", help="Preview without applying")        with open(file_path, "a", encoding="utf-8") as f:

    parser.add_argument("--open-pr", action="store_true", help="Open PR via gh CLI (if available)")            f.write(content)

    args = parser.parse_args()    elif patch.startswith("PATCH:UNIFIED\n"):

        # Minimal unified patch apply: defer to 'git apply' if available

    if not BUILDER.exists():        tmp = ROOT / ".tmp.plan.patch"

        print("[apply_plan] ERROR: evolver/builder.py introuvable", file=sys.stderr)        tmp.write_text(patch.split("\n", 1)[1], encoding="utf-8")

        return 2        try:

    if not (ROOT / args.plan).exists():            import subprocess

        print(f"[apply_plan] WARNING: plan {args.plan} absent – rien à appliquer (0)")

        return 0            subprocess.run(["git", "apply", "--whitespace=fix", str(tmp)], cwd=str(ROOT), check=True)

        finally:

    # Re-exec builder with appropriate arguments            try:

    cmd = [sys.executable, str(BUILDER), args.plan]                tmp.unlink()

    if args.dry_run:            except Exception:

        cmd.append("--dry-run")                pass

    if args.open_pr:    else:

        cmd.append("--open-pr")        raise ValueError("Unsupported patch format")

    print("[apply_plan] Running:", " ".join(cmd))

    return_code = 0

    try:def main() -> None:

        return_code = __import__("subprocess").run(cmd, check=False).returncode    plan_path = ROOT / "evolver_plan.json"

    except Exception as e:    plan: Dict[str, Any] = json.loads(plan_path.read_text(encoding="utf-8"))

        print(f"[apply_plan] EXCEPTION: {e}", file=sys.stderr)    for ch in plan.get("changes", []) or []:

        return_code = 1        rel = ch.get("file")

    return return_code        patch = ch.get("patch", "")

        if not rel or not patch:

            continue

if __name__ == "__main__":        fp = ROOT / rel

    raise SystemExit(main())        apply_patch(fp, patch)

    # Write proposed tests if provided
    for t in plan.get("tests", []) or []:
        f = t.get("file")
        c = t.get("content", "")
        if not f:
            continue
        fp = ROOT / f
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(c, encoding="utf-8")


if __name__ == "__main__":
    main()
