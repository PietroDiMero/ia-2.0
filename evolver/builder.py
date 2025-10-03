from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any


ROOT = Path(__file__).resolve().parents[1]


def sh(cmd: str, check: bool = True) -> str:
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=str(ROOT))
    if check and p.returncode != 0:
        raise RuntimeError(f"Command failed: {cmd}\n{p.stdout}\n{p.stderr}")
    return (p.stdout or "") + (p.stderr or "")


def load_plan(plan_path: Path) -> Dict[str, Any]:
    return json.loads(plan_path.read_text(encoding="utf-8"))


def ensure_branch(branch: str) -> None:
    sh("git rev-parse --git-dir >NUL 2>&1 || git init", check=False)
    # Fetch origin if exists
    sh("git fetch origin", check=False)
    # Create/checkout branch
    sh(f"git checkout -B {branch}")


def apply_patch(file_path: Path, patch: str, dry_run: bool) -> None:
    # Supported formats from mentor: PATCH:WRITE, PATCH:APPEND, PATCH:UNIFIED
    if patch.startswith("PATCH:WRITE\n"):
        content = patch.split("\n", 1)[1]
        if dry_run:
            print(f"[DRY] write {file_path} ({len(content)} bytes)")
            return
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
    elif patch.startswith("PATCH:APPEND\n"):
        content = patch.split("\n", 1)[1]
        if dry_run:
            print(f"[DRY] append {file_path} (+{len(content)} bytes)")
            return
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(content)
    elif patch.startswith("PATCH:UNIFIED\n"):
        unified = patch.split("\n", 1)[1]
        if dry_run:
            print(f"[DRY] apply unified patch to {file_path} (len={len(unified)})")
            return
        # Try to apply with `git apply -p0` from repo root
        tmp = ROOT / ".tmp.patch"
        tmp.write_text(unified, encoding="utf-8")
        try:
            sh(f"git apply --whitespace=fix {tmp}")
        finally:
            try:
                tmp.unlink()
            except Exception:
                pass
    else:
        raise ValueError("Unsupported patch format")


def stage_and_commit(message: str) -> None:
    sh("git add -A")
    sh(f"git commit -m {json.dumps(message)}", check=False)


def open_pr(title: str, body: str) -> None:
    # Requires GitHub CLI `gh` to be authenticated. Fallback prints instructions.
    try:
        sh(f"gh pr create --title {json.dumps(title)} --body {json.dumps(body)} --fill", check=True)
    except Exception as e:
        print("Impossible d'ouvrir la PR automatiquement (gh CLI).\n", e)
        print("Crée la PR manuellement sur GitHub avec le titre et la description ci-dessus.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Apply an evolver plan and open a PR")
    ap.add_argument("plan", type=str, help="Path to evolver_plan.json")
    ap.add_argument("--dry-run", action="store_true", help="Preview patches without writing")
    ap.add_argument("--open-pr", action="store_true", help="Open a GitHub PR using gh CLI")
    args = ap.parse_args()

    plan_path = Path(args.plan)
    plan = load_plan(plan_path)

    branch = f"auto-update/{datetime.utcnow().strftime('%Y%m%d')}"
    ensure_branch(branch)

    # Apply changes
    changes = plan.get("changes", [])
    for ch in changes:
        rel = ch.get("file")
        patch = ch.get("patch", "")
        if not rel or not patch:
            continue
        fp = ROOT / rel
        apply_patch(fp, patch, args.dry_run)

    if not args.dry_run:
        # Write proposed tests if provided
        for t in plan.get("tests", []) or []:
            f = t.get("file")
            c = t.get("content", "")
            if not f:
                continue
            fp = ROOT / f
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(c, encoding="utf-8")
        stage_and_commit(plan.get("title", "auto-update"))

    # Push branch
    if not args.dry_run:
        sh(f"git push -u origin {branch}")

    if args.open_pr and not args.dry_run:
        title = plan.get("title", branch)
        # Simple body from rationale and checklist
        rationale = plan.get("rationale", "")
        checklist = "\n".join(f"- [ ] {c.get('file')} ({c.get('hazard','low')})" for c in changes)
        body = f"{rationale}\n\nChanges:\n{checklist}\n"
        open_pr(title, body)

    print("Terminé.")


if __name__ == "__main__":
    main()
