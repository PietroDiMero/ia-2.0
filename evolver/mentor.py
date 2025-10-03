from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any


ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Change:
    file: str
    patch: str  # See builder.py for supported patch formats
    hazard: str  # low | medium | high


def _read_text_if_exists(p: Path) -> str:
    try:
        if p.exists():
            return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        pass
    return ""


def _collect_files(base: Path, exts: List[str]) -> List[Path]:
    files: List[Path] = []
    if not base.exists():
        return files
    for ext in exts:
        files.extend(base.rglob(f"*{ext}"))
    return files


def _summarize_issues(issues_text: str) -> str:
    if not issues_text.strip():
        return "Aucun issues.md trouvé. Plan basé sur une inspection superficielle du code."
    # Keep a short sanitized rationale
    lines = [l.strip() for l in issues_text.splitlines() if l.strip()]
    head = " ".join(lines[:10])
    return f"Synthèse issues.md: {head[:300]}{'…' if len(head)>300 else ''}"


def _propose_changes(files: List[Path]) -> List[Change]:
    changes: List[Change] = []
    # This mentor proposes non-destructive housekeeping patches as a starting point.
    # Patch format supported by builder:
    # - PATCH:WRITE\n<file content>  (create/overwrite)
    # - PATCH:APPEND\n<content to append>
    # - PATCH:UNIFIED\n<unified diff>

    # Example: if a Python file lacks module docstring, propose adding one at top.
    for p in files:
        if p.suffix == ".py":
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
                if not text.lstrip().startswith(("\"\"\"", "'''")):
                    new_first = f'"""Auto-added module docstring for {p.name}."""\n\n'
                    patch = "PATCH:WRITE\n" + (new_first + text)
                    rel = str(p.relative_to(ROOT))
                    changes.append(Change(file=rel, patch=patch, hazard="low"))
            except Exception:
                continue
    return changes


def generate_plan() -> Dict[str, Any]:
    backend_dir = ROOT / "backend"
    crawler_dir = ROOT / "crawler"
    frontend_dir = ROOT / "frontend"
    issues_md = ROOT / "issues.md"

    backend_files = _collect_files(backend_dir, [".py"])
    crawler_files = _collect_files(crawler_dir, [".py"])
    frontend_files = _collect_files(frontend_dir, [".js", ".jsx", ".ts", ".tsx"])
    all_files = backend_files + crawler_files + frontend_files

    issues_text = _read_text_if_exists(issues_md)
    rationale = _summarize_issues(issues_text)

    changes = _propose_changes(all_files)

    plan: Dict[str, Any] = {
        "title": f"Auto-update plan {datetime.utcnow().strftime('%Y-%m-%d')} ({len(changes)} changements)",
        "rationale": rationale,
        "changes": [asdict(c) for c in changes],
        # tests can be a free-form list; here we suggest placeholders
        "tests": [
            {
                "file": "tests/test_smoke_backend.py",
                "content": (
                    "import requests\n\n"
                    "def test_health():\n"
                    "    r = requests.get('http://localhost:8000/health', timeout=5)\n"
                    "    assert r.ok and r.json().get('status') == 'ok'\n"
                ),
            }
        ],
    }
    return plan


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an auto-update plan JSON from repo state")
    parser.add_argument("--out", type=str, default="evolver_plan.json", help="Output plan JSON path")
    args = parser.parse_args()

    plan = generate_plan()
    out_path = Path(args.out)
    out_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Plan écrit: {out_path}")


if __name__ == "__main__":
    main()
