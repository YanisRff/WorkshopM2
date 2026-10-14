"""
telemetry.py — Enregistrement et analyse télémétrique des parties.

Capture l'évolution du jeu tour par tour, les ordres rejetés,
les dégâts, l'économie et produit un diagnostic post-mortem.
"""

from collections import Counter
import json
import os
from typing import Any, Dict, List, Optional


class MatchLogger:
    def __init__(self, log_path: Optional[str] = None):
        self.log_path = log_path
        self.game_id = ""
        self.team = ""
        self.name = ""
        self.rules: Dict[str, Any] = {}
        self.history: List[Dict[str, Any]] = []
        self.rejections: List[Dict[str, Any]] = []
        self.macro_states: List[str] = []
        self.winner: Optional[str] = None
        self.reason: Optional[str] = None

    def record_start(self, game_id: str, team: str, name: str, rules: Dict[str, Any]):
        self.game_id = game_id
        self.team = team
        self.name = name
        self.rules = rules

    def record_moves(self, turn: int, state: Dict[str, Any], events: List[Dict[str, Any]],
                     rejected: List[Dict[str, Any]], moves: List[Dict[str, Any]]):
        if rejected:
            for r in rejected:
                self.rejections.append({"turn": turn, "phase": "moves", "rejection": r})

        # Extraire les métriques de base
        my_team = state.get("teams", {}).get(self.team, {})
        my_castle = next((b for b in state.get("buildings", []) if b["team"] == self.team), {})
        enemy_castle = next((b for b in state.get("buildings", []) if b["team"] != self.team), {})

        self.history.append({
            "turn": turn,
            "phase": "moves",
            "gold": my_team.get("resources", {}).get("gold", 0),
            "meat": my_team.get("resources", {}).get("meat", 0),
            "wood": my_team.get("resources", {}).get("wood", 0),
            "castle_hp": my_castle.get("hp", 0),
            "enemy_castle_hp": enemy_castle.get("hp", 0),
            "unit_count": my_team.get("unit_count", 0),
            "moves_count": len(moves),
            "events_count": len(events)
        })

    def record_actions(self, turn: int, state: Dict[str, Any], events: List[Dict[str, Any]],
                       rejected: List[Dict[str, Any]], actions: List[Dict[str, Any]],
                       macro_state: str):
        if rejected:
            for r in rejected:
                self.rejections.append({"turn": turn, "phase": "actions", "rejection": r})

        self.macro_states.append(macro_state)

        if self.history and self.history[-1]["turn"] == turn:
            self.history[-1]["actions_count"] = len(actions)
            self.history[-1]["macro_state"] = macro_state

    def record_end(self, winner: Optional[str], reason: Optional[str], state: Optional[Dict[str, Any]],
                   events: List[Dict[str, Any]], rejected: List[Dict[str, Any]]):
        self.winner = winner
        self.reason = reason
        if rejected:
            for r in rejected:
                self.rejections.append({"turn": -1, "phase": "end", "rejection": r})

        if not self.log_path:
            return

        report = self.generate_analysis(state)
        os.makedirs(os.path.dirname(os.path.abspath(self.log_path)), exist_ok=True)
        with open(self.log_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

    def generate_analysis(self, final_state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Génère un diagnostic analytique complet de la partie."""
        is_victory = (self.winner == self.team)
        is_draw = (self.winner == "draw")
        result_str = "Victoire" if is_victory else ("Nul" if is_draw else "Défaite")

        # Analyse des rejets
        rejection_reasons = Counter()
        for r in self.rejections:
            reason = r.get("rejection", {}).get("reason", "inconnu")
            rejection_reasons[reason] += 1

        # Analyse macro
        macro_distribution = dict(Counter(self.macro_states))

        # Évolution du château
        castle_hp_curve = [h["castle_hp"] for h in self.history if "castle_hp" in h]
        enemy_castle_hp_curve = [h["enemy_castle_hp"] for h in self.history if "enemy_castle_hp" in h]

        # Points critiques / Diagnostic
        critiques: List[str] = []
        recommendations: List[str] = []

        if not is_victory and not is_draw:
            if self.reason == "castle_destroyed":
                critiques.append("Le château a été détruit par l'armée adverse.")
                if macro_distribution.get("DEFENSE_URGENTE", 0) == 0 and macro_distribution.get("DEFENSE", 0) <= 2:
                    recommendations.append("L'état DEFENSE s'est déclenché trop tard ou pas assez longtemps.")
            elif self.reason == "max_turns":
                critiques.append(f"Limite des 500 tours atteinte avec moins de PV ({castle_hp_curve[-1] if castle_hp_curve else 0} vs {enemy_castle_hp_curve[-1] if enemy_castle_hp_curve else 0}).")
                recommendations.append("Augmenter l'agressivité en milieu/fin de partie pour entamer le château adverse.")
            elif self.reason == "opponent_disconnected":
                critiques.append("Déconnexion de l'adversaire.")

        if rejection_reasons:
            for reason, count in rejection_reasons.most_common(3):
                critiques.append(f"{count} ordres rejetés pour la raison : '{reason}'")
            recommendations.append("Corriger les préconditions dans pathfinding ou micro pour éviter ces rejets.")

        return {
            "game_id": self.game_id,
            "team": self.team,
            "name": self.name,
            "result": result_str,
            "winner": self.winner,
            "end_reason": self.reason,
            "total_turns": len(self.history),
            "macro_distribution": macro_distribution,
            "rejections_total": len(self.rejections),
            "rejections_by_reason": dict(rejection_reasons),
            "rejections_details": self.rejections[:20],  # Les 20 premiers
            "critiques": critiques,
            "recommendations": recommendations,
            "telemetry_timeline": self.history
        }
