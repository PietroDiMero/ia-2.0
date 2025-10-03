"""
Module de stratégie pour l'IA auto‑évolutive.

Ce module est volontairement simple et peut être régénéré automatiquement
par l'evolver pour ajuster les hyper‑paramètres. Il expose une classe
Strategy avec des bornes de seuil et des pas d'ajustement.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Strategy:
    # Hyper‑paramètres par défaut (peuvent être réécrits par l'evolver)
    threshold_min: float = 0.05
    threshold_max: float = 0.5
    step_success: float = 0.02
    step_fail: float = 0.02
    top_k: int = 3

    def adjust_threshold(self, current: float, success: bool) -> float:
        """Retourne un nouveau seuil en fonction du succès."""
        if success:
            current = max(self.threshold_min, current - self.step_success)
        else:
            current = min(self.threshold_max, current + self.step_fail)
        return float(round(current, 6))

    def settings(self) -> dict:
        return {
            "threshold_min": self.threshold_min,
            "threshold_max": self.threshold_max,
            "step_success": self.step_success,
            "step_fail": self.step_fail,
            "top_k": self.top_k,
        }
