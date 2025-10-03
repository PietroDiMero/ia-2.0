from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

import requests


def run(cmd: List[str], cwd: Optional[Path] = None, check: bool = True) -> subprocess.CompletedProcess:
    print("[evolver] $", " ".join(cmd))
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=check, capture_output=True, text=True)


def gather_sources(root: Path) -> List[Path]:
    """Collect backend and crawler sources to analyze."""
    files: List[Path] = []
    for rel in ["backend", "crawler"]:
        d = root / rel
        if d.exists():
            for p in d.rglob("*.py"):
                if "/.venv/" in str(p).replace("\\", "/"):
                    continue
                files.append(p)
    return files


def openai_propose_patch(prompt: str, api_key: str, model: str = "gpt-4o-mini") -> str:
    try:
        from openai import OpenAI  # type: ignore
    except Exception as e:
        raise RuntimeError("openai package is required") from e
    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        temperature=0.2,
        messages=[
            {"role": "system", "content": "You are a senior software engineer generating high quality git unified diffs."},
            {"role": "user", "content": prompt},
        ],
    )
    return (resp.choices[0].message.content or "").strip()


def build_prompt(root: Path, files: List[Path]) -> str:
    parts = [
        "Propose a small, safe improvement to performance/refactor or add a tiny endpoint.",
        "Return ONLY a single unified diff patch (git format), no extra prose.",
        "Use correct file paths relative to repository root.",
    ]
    for p in files[:20]:
        try:
            text = p.read_text(encoding="utf-8")[:8000]
        except Exception:
            continue
        rel = p.relative_to(root).as_posix()
        parts.append(f"\n--- FILE: {rel} ---\n{text}")
    return "\n".join(parts)


def create_branch_and_apply(repo: Path, patch_text: str, branch: str) -> Optional[str]:
    try:
        run(["git", "fetch", "origin"], cwd=repo, check=False)
        run(["git", "checkout", "-b", branch], cwd=repo)
        # Write patch to file
        patches_dir = repo / "real-time-ai-dashboard" / "evolver" / "patches"
        patches_dir.mkdir(parents=True, exist_ok=True)
        patch_file = patches_dir / f"{branch}.diff"
        patch_file.write_text(patch_text, encoding="utf-8")
        # Try to apply
        apply = run(["git", "apply", str(patch_file)], cwd=repo, check=False)
        if apply.returncode != 0:
            print("[evolver] git apply failed:\n", apply.stderr)
            return None
        run(["git", "add", "-A"], cwd=repo)
        run(["git", "commit", "-m", f"AI-EVOLVER: {branch}"], cwd=repo)
        run(["git", "push", "-u", "origin", branch], cwd=repo)
        return str(patch_file)
    except subprocess.CalledProcessError as e:
        print("[evolver] git error:", e.stderr)
        return None


def create_pr(branch: str, token: str, repo_full: str, title: str, body: str) -> Optional[dict]:
    url = f"https://api.github.com/repos/{repo_full}/pulls"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    data = {"title": title, "head": branch, "base": "main", "body": body}
    r = requests.post(url, headers=headers, json=data, timeout=30)
    if r.status_code in (200, 201):
        return r.json()
    print("[evolver] PR creation failed:", r.status_code, r.text)
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[2]  # repository root
    rt_root = repo / "real-time-ai-dashboard"
    files = gather_sources(rt_root)
    if not files:
        print("[evolver] no source files found")
        return 0

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        print("[evolver] OPENAI_API_KEY not set; aborting")
        return 0

    prompt = build_prompt(rt_root, files)
    patch_text = openai_propose_patch(prompt, api_key)
    today = dt.datetime.utcnow().strftime("%Y%m%d")
    branch = f"auto-update/{today}"

    if args.dry_run:
        print(patch_text[:2000])
        return 0

    patch_file = create_branch_and_apply(repo, patch_text, branch)
    if not patch_file:
        print("[evolver] no patch applied; exiting")
        return 0

    gh_token = os.getenv("GITHUB_TOKEN", "")
    repo_full = os.getenv("GITHUB_REPOSITORY", "")  # owner/repo
    pr_json = None
    if gh_token and repo_full:
        pr_json = create_pr(branch, gh_token, repo_full, title=f"AI Evolver {today}", body=f"Patch: {Path(patch_file).name}")

    history_path = rt_root / "evolver" / "history.json"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history = []
    if history_path.exists():
        try:
            history = json.loads(history_path.read_text(encoding="utf-8"))
        except Exception:
            history = []
    entry = {
        "timestamp": dt.datetime.utcnow().isoformat() + "Z",
        "branch": branch,
        "patch_file": str(Path(patch_file).relative_to(repo)) if patch_file else None,
        "pr": pr_json,
    }
    history.append(entry)
    history_path.write_text(json.dumps(history, indent=2), encoding="utf-8")
    # Also write last_pr.json for workflow consumption
    (rt_root / "evolver" / "last_pr.json").write_text(json.dumps(entry, indent=2), encoding="utf-8")
    print("[evolver] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
