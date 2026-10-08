"""Strategie globale deterministe pour le protocole de REGLES.md.

API du bot : analyze_state(state, rules, team), get_multipliers(strategy).
API detaillee : analyze_macro(state, rules, team, previous_state=None).
Les statistiques proviennent de rules.units ; stocks et cout viande de
state.teams ; chateaux de state.buildings. Aucun parcours de la grille.
Les menaces utilisent la distance de Chebyshev au rectangle du chateau :
c'est une estimation prudente qui ignore les obstacles, pas un chemin.
"""

from dataclasses import dataclass
from math import inf
from typing import Any, Mapping, Optional


# Cles partagees avec micro.py et economy.py.
WEIGHTS = {
    "ECO_FOCUS": {
        "attack": 0.8, "heal": 1.0, "gather": 2.5, "deposit": 3.0,
        "move_defend": 0.8, "move_assault": 0.5, "move_resource": 2.0,
        "recruit_pawn": 2.5, "recruit_military": 0.8, "repair": 1.0,
    },
    "DEFENSE_URGENTE": {
        "attack": 5.0, "heal": 3.0, "gather": 0.5, "deposit": 3.0,
        "move_defend": 5.0, "move_assault": 0.2, "move_resource": 0.4,
        "recruit_pawn": 0.3, "recruit_military": 4.0, "repair": 5.0,
    },
    "DEFENSE": {
        "attack": 2.5, "heal": 2.0, "gather": 1.0, "deposit": 2.0,
        "move_defend": 3.0, "move_assault": 0.5, "move_resource": 1.0,
        "recruit_pawn": 0.7, "recruit_military": 2.5, "repair": 2.0,
    },
    "EQUILIBRE": {
        "attack": 1.5, "heal": 1.5, "gather": 1.5, "deposit": 2.0,
        "move_defend": 1.5, "move_assault": 1.0, "move_resource": 1.5,
        "recruit_pawn": 1.0, "recruit_military": 1.5, "repair": 1.5,
    },
    "ASSAUT": {
        "attack": 3.0, "heal": 2.0, "gather": 0.8, "deposit": 2.0,
        "move_defend": 1.0, "move_assault": 3.0, "move_resource": 0.8,
        "recruit_pawn": 0.5, "recruit_military": 2.5, "repair": 1.0,
    },
}


@dataclass(frozen=True)
class MacroConfig:
    # Heuristiques a ajuster pendant les parties.
    target_pawns: int = 3
    defense_radius: int = 7
    critical_radius: int = 2
    minimum_military_units: int = 2
    defense_exit_margin: int = 2
    critical_hp_ratio: float = 0.35
    assault_ratio: float = 1.5
    assault_keep_ratio: float = 1.2
    minimum_local_ratio: float = 0.8


@dataclass(frozen=True)
class Metrics:
    castle_hp: float
    castle_max_hp: float
    castle_hp_ratio: float
    gold: float
    meat: float
    wood: float
    next_meat_cost: float
    pawn_count: int
    military_count: int
    own_damage: float
    enemy_damage: float
    military_ratio: float
    nearest_enemy_distance: float
    nearest_attacker_distance: float
    nearby_own_damage: float
    nearby_enemy_damage: float
    local_military_ratio: float
    immediate_enemy_damage: float
    threatened: bool


def get_chebyshev_distance(a: Mapping, b: Mapping) -> int:
    return max(abs(a["x"] - b["x"]), abs(a["y"] - b["y"]))


def _ratio(own: float, enemy: float) -> float:
    # Deux armees vides ne constituent pas une superiorite militaire.
    if enemy == 0:
        return inf if own > 0 else 1.0
    return own / enemy


def get_castle_distance(unit: Mapping, castle: Mapping) -> int:
    """Distance minimale entre une unite et toutes les cases du chateau."""
    dx = max(castle["x"] - unit["x"],
             unit["x"] - (castle["x"] + castle["width"] - 1), 0)
    dy = max(castle["y"] - unit["y"],
             unit["y"] - (castle["y"] + castle["height"] - 1), 0)
    return max(dx, dy)


def _stat(unit: Mapping, name: str, unit_stats: Mapping) -> float:
    # Les PV sont dans state ; attaque et portee sont dans rules.
    value = float(unit_stats[unit["type"]][name])
    if value < 0:
        raise ValueError(f"Statistique {name!r} negative")
    return value


def extract_metrics(
    state: Mapping[str, Any],
    rules: Mapping[str, Any],
    team: str,
    config: Optional[MacroConfig] = None,
    previous_state: Optional[str] = None,
) -> Metrics:
    """Extrait les metriques depuis le protocole reel du serveur.

    Complexite O(nombre d'unites), memoire auxiliaire constante.
    Les unites mortes sont exclues. Les moines sans degats n'ajoutent
    aucune puissance militaire et ne declenchent pas une menace d'attaque.
    """
    cfg = config or MacroConfig()
    stats = rules["units"]
    castle = next(b for b in state["buildings"]
                  if b["team"] == team and b["type"] == "castle")
    team_state = state["teams"][team]
    bank = team_state["resources"]
    hp = float(castle["hp"])
    max_hp = float(castle["max_hp"])
    if max_hp <= 0:
        raise ValueError("Les PV maximum du chateau doivent etre positifs")

    own_damage = enemy_damage = 0.0
    nearby_own = nearby_enemy = immediate = 0.0
    nearest_enemy = nearest_attacker = inf
    pawns = military_count = 0
    threatened = False
    # Hysteresis : sortir de defense demande une distance plus grande.
    radius = cfg.defense_radius
    if previous_state in ("DEFENSE", "DEFENSE_URGENTE"):
        radius += cfg.defense_exit_margin

    for unit in state["units"]:
        if unit["hp"] <= 0:
            continue
        damage = _stat(unit, "attack", stats)
        distance = get_castle_distance(unit, castle)
        if unit["team"] == team:
            own_damage += damage
            pawns += unit["type"] == "pawn"
            military_count += unit["type"] != "pawn" and damage > 0
            if distance <= radius:
                nearby_own += damage
            continue
        enemy_damage += damage
        nearest_enemy = min(nearest_enemy, distance)
        if damage == 0:
            continue
        attack_range = _stat(unit, "range", stats)
        nearest_attacker = min(nearest_attacker, distance)
        # Inclure les tireurs dont la portee depasse le rayon habituel.
        if distance <= max(radius, attack_range + 1):
            nearby_enemy += damage
            threatened = True
        if distance <= attack_range:
            immediate += damage

    return Metrics(
        castle_hp=hp,
        castle_max_hp=max_hp,
        castle_hp_ratio=hp / max_hp,
        gold=float(bank["gold"]),
        meat=float(bank["meat"]),
        wood=float(bank["wood"]),
        next_meat_cost=float(team_state["next_meat_cost"]),
        pawn_count=pawns,
        military_count=military_count,
        own_damage=own_damage,
        enemy_damage=enemy_damage,
        military_ratio=_ratio(own_damage, enemy_damage),
        nearest_enemy_distance=nearest_enemy,
        nearest_attacker_distance=nearest_attacker,
        nearby_own_damage=nearby_own,
        nearby_enemy_damage=nearby_enemy,
        local_military_ratio=_ratio(nearby_own, nearby_enemy),
        immediate_enemy_damage=immediate,
        threatened=threatened,
    )


def choose_state(
    metrics: Metrics,
    config: Optional[MacroConfig] = None,
    previous_state: Optional[str] = None,
) -> str:
    cfg = config or MacroConfig()
    m = metrics
    if m.threatened:
        if (
            m.immediate_enemy_damage > 0
            or m.nearest_attacker_distance <= cfg.critical_radius
            or m.castle_hp_ratio <= cfg.critical_hp_ratio
            or m.local_military_ratio < cfg.minimum_local_ratio
        ):
            return "DEFENSE_URGENTE"
        return "DEFENSE"

    if m.pawn_count < cfg.target_pawns or m.own_damage == 0:
        return "ECO_FOCUS"

    assault_threshold = (
        cfg.assault_keep_ratio if previous_state == "ASSAUT"
        else cfg.assault_ratio
    )
    if (m.military_count >= cfg.minimum_military_units
            and m.military_ratio >= assault_threshold):
        return "ASSAUT"
    if m.meat < m.next_meat_cost:
        return "ECO_FOCUS"
    return "EQUILIBRE"


def analyze_macro(
    state: Mapping[str, Any],
    rules: Mapping[str, Any],
    team: str,
    config: Optional[MacroConfig] = None,
    previous_state: Optional[str] = None,
) -> dict:
    """Retourne l'etat, les poids et les metriques pour les autres modules.

    Objet interne au bot, a ne pas envoyer comme action au serveur.
    """
    metrics = extract_metrics(state, rules, team, config, previous_state)
    strategy = choose_state(metrics, config, previous_state)
    return {
        "state": strategy,
        "weights": get_multipliers(strategy),
        "metrics": metrics,
    }


def analyze_state(
    state: Mapping[str, Any],
    rules: Mapping[str, Any],
    team: str,
    previous_state: Optional[str] = None,
    config: Optional[MacroConfig] = None,
) -> str:
    """Interface simple compatible avec le bot et le Logisticien."""
    metrics = extract_metrics(state, rules, team, config, previous_state)
    return choose_state(metrics, config, previous_state)


def get_multipliers(macro_state: str) -> dict:
    """Poids independants ; inclut les trois ressources attendues par micro."""
    # Alias pour les modules de l'equipe utilisant encore le nom initial.
    if macro_state == "DEVELOPPEMENT":
        macro_state = "ECO_FOCUS"
    weights = WEIGHTS[macro_state].copy()
    for resource in ("wood", "gold", "meat"):
        weights["gather_" + resource] = weights["gather"]
    return weights
