from __future__ import annotations

import argparse
import time
from typing import List

import requests


def main():
    p = argparse.ArgumentParser(description="Auto update / auto learning loop for the Flask AI server")
    p.add_argument("--base-url", default="http://127.0.0.1:8000", help="Base URL of the Flask server")
    p.add_argument("--iterations", type=int, default=3, help="Number of evolve cycles to run (0 for infinite)")
    p.add_argument("--sleep", type=float, default=5.0, help="Seconds to sleep between cycles")
    p.add_argument(
        "--questions",
        nargs="*",
        default=[
            "Qu'est-ce qu'un agent auto-évolutif ?",
            "Qu'est-ce que EvoAgentX ?",
            "Comment fonctionne le Darwin Gödel Machine ?",
            "Qu'est-ce que AlphaEvolve ?",
        ],
        help="Seed questions to drive learning",
    )
    args = p.parse_args()

    base = args.base_url.rstrip("/")

    # Health check
    try:
        r = requests.get(f"{base}/api/status", timeout=5)
        r.raise_for_status()
    except Exception as e:
        print("[auto_update] Erreur de connexion au serveur Flask.")
        print("Assurez-vous qu'il est démarré: python server.py")
        print(f"Détail: {e}")
        return 2

    # Ensure worker running
    st = requests.get(f"{base}/api/status", timeout=10).json()
    if not st.get("running"):
        print("[auto_update] Démarrage du worker…")
        requests.post(f"{base}/api/start", timeout=10)

    def ask_all(questions: List[str]):
        for q in questions:
            try:
                resp = requests.post(f"{base}/api/ask", json={"question": q}, timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    print(f"[ask] {q} -> success={data.get('success')} threshold={data.get('threshold'):.3f}")
                else:
                    print(f"[ask] {q} -> HTTP {resp.status_code}")
            except Exception as e:
                print(f"[ask] {q} -> erreur: {e}")

    cycle = 0
    while True:
        cycle += 1
        print(f"\n=== Cycle {cycle} ===")
        ask_all(args.questions)

        # Trigger evolution
        try:
            ev = requests.post(f"{base}/api/evolve", timeout=15).json()
            change = ev.get("change")
            if change:
                print(f"[evolve] {change['tuned']} {change['from']} -> {change['to']} (mean_success={ev.get('mean_success'):.2f})")
            else:
                print(f"[evolve] aucune modification (mean_success={ev.get('mean_success'):.2f})")
        except Exception as e:
            print(f"[evolve] erreur: {e}")

        if args.iterations and cycle >= args.iterations:
            break
        time.sleep(max(0.0, args.sleep))

    print("\n[auto_update] Terminé.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
