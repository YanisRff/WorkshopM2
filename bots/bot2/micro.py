"""
micro.py — Gestion tactique des unités et scoring d'actions (Utility AI).

Chaque unité évalue toutes ses actions légales et choisit celle qui a le score le plus élevé.
Implémente la Règle d'or du combat : Focus Fire (suivi des PV virtuels pour éviter l'overkill).
"""

from typing import Any, Dict, List, Mapping, Optional


def _chebyshev(x1: int, y1: int, x2: int, y2: int) -> int:
    return max(abs(x1 - x2), abs(y1 - y2))


def _dist_to_castle(px: int, py: int, castle: Mapping[str, Any]) -> int:
    rx, ry = castle["x"], castle["y"]
    rw, rh = castle["width"], castle["height"]
    dx = max(rx - px, 0, px - (rx + rw - 1))
    dy = max(ry - py, 0, py - (ry + rh - 1))
    return max(dx, dy)


def generate_and_score_actions(
    state: Mapping[str, Any],
    rules: Mapping[str, Any],
    team: str,
    multipliers: Mapping[str, float],
) -> List[Dict[str, Any]]:
    """
    Génère et évalue les actions pour chaque unité vivante de notre camp.
    Applique le focus fire via un dictionnaire de PV virtuels.
    """
    my_castle = next(
        (b for b in state.get("buildings", []) if b["team"] == team and b["type"] == "castle"),
        None,
    )
    enemy_castle = next(
        (b for b in state.get("buildings", []) if b["team"] != team and b["type"] == "castle"),
        None,
    )

    my_units = [u for u in state.get("units", []) if u["team"] == team and u.get("hp", 0) > 0]
    enemy_units = [u for u in state.get("units", []) if u["team"] != team and u.get("hp", 0) > 0]

    # Tracker de PV virtuels pour les ennemis (Focus Fire)
    virtual_enemy_hp: Dict[int, int] = {e["id"]: int(e["hp"]) for e in enemy_units}
    virtual_castle_hp: int = int(enemy_castle["hp"]) if enemy_castle else 0

    unit_stats = rules.get("units", {}) if rules else {}
    default_stats = {
        "pawn": {"attack": 3, "heal": 0, "range": 1},
        "warrior": {"attack": 8, "heal": 0, "range": 1},
        "lancer": {"attack": 10, "heal": 0, "range": 2},
        "archer": {"attack": 9, "heal": 0, "range": 4},
        "monk": {"attack": 0, "heal": 10, "range": 2},
    }

    # Poids depuis macro
    w_attack = multipliers.get("attack", 1.0)
    w_heal = multipliers.get("heal", 1.0)
    w_deposit = multipliers.get("deposit", 1.0)
    w_gather_gold = multipliers.get("gather_gold", multipliers.get("gather", 1.0))
    w_gather_meat = multipliers.get("gather_meat", multipliers.get("gather", 1.0))
    w_gather_wood = multipliers.get("gather_wood", multipliers.get("gather", 1.0))

    actions: List[Dict[str, Any]] = []

    for u in my_units:
        u_id = u["id"]
        u_type = u["type"]
        ux, uy = u["x"], u["y"]

        stats = unit_stats.get(u_type, default_stats.get(u_type, {}))
        attack_dmg = stats.get("attack", 0)
        heal_power = stats.get("heal", 0)
        reach = stats.get("range", 1)

        best_action: Optional[Dict[str, Any]] = None
        best_score: float = 0.0

        # ====================================================================
        # 1. Actions spécifiques aux Pions : Deposit & Gather
        # ====================================================================
        if u_type == "pawn":
            carrying = u.get("carrying")
            carried_amount = carrying["amount"] if carrying else 0
            carried_res = carrying["resource"] if carrying else None

            # --- DEPOSIT ---
            if my_castle and my_castle.get("hp", 0) > 0 and carried_amount > 0:
                dist_c = _dist_to_castle(ux, uy, my_castle)
                if dist_c <= 1:
                    # Plus le pion a de ressources, plus le score est élevé
                    score_deposit = (50.0 + carried_amount * 20.0) * w_deposit
                    if score_deposit > best_score:
                        best_score = score_deposit
                        best_action = {"type": "deposit", "unit": u_id}

            # --- GATHER ---
            if carried_amount < 5:
                bank = state.get("teams", {}).get(team, {}).get("resources", {})
                next_meat = state.get("teams", {}).get(team, {}).get("next_meat_cost", 1)
                curr_gold = bank.get("gold", 0)
                curr_meat = bank.get("meat", 0)

                for r in state.get("resources", []):
                    rx, ry = r["x"], r["y"]
                    r_kind = r["resource"]

                    # Le bois ne sert qu'à réparer le château : interdire sa récolte si le château est en bon état
                    if r_kind == "wood":
                        if not my_castle or my_castle.get("hp", 800) >= my_castle.get("max_hp", 800) - 40:
                            continue

                    # Si les mains sont vides, ne pas récolter une ressource en surplus au détriment de la ressource manquante
                    if carried_res is None:
                        if curr_gold >= 10 and curr_meat < next_meat and r_kind == "gold":
                            continue  # On a déjà l'or, on doit impérativement ramasser la viande !
                        if curr_meat >= next_meat and curr_gold < 5 and r_kind == "meat":
                            continue  # On a déjà la viande, on doit impérativement ramasser l'or !

                    # Doit être à portée 1 (Chebyshev)
                    if _chebyshev(ux, uy, rx, ry) <= 1:
                        # Ne peut récolter que la même ressource s'il en porte déjà
                        if carried_res is None or carried_res == r_kind:
                            if r_kind == "gold":
                                mult_g = w_gather_gold
                            elif r_kind == "meat":
                                mult_g = w_gather_meat
                            else:
                                mult_g = w_gather_wood

                            # Score de récolte (inversement proportionnel à ce qu'il a déjà pour favoriser le flux)
                            score_gather = (30.0 + (5 - carried_amount) * 5.0) * mult_g
                            if score_gather > best_score:
                                best_score = score_gather
                                best_action = {
                                    "type": "gather",
                                    "unit": u_id,
                                    "target": [rx, ry],
                                }

        # ====================================================================
        # 2. Action des Moines : Heal
        # ====================================================================
        if heal_power > 0:
            for ally in my_units:
                max_hp = ally.get("max_hp", 0)
                hp = ally.get("hp", 0)
                if hp < max_hp:
                    dist_a = _chebyshev(ux, uy, ally["x"], ally["y"])
                    if dist_a <= reach:
                        missing = max_hp - hp
                        ally_type = ally.get("type", "")
                        type_heal_bonus = {
                            "lancer": 50.0,
                            "monk": 40.0,
                            "archer": 35.0,
                            "warrior": 30.0,
                            "pawn": 5.0,
                        }.get(ally_type, 10.0)
                        # Priorité aux unités d'élite et les plus blessées
                        score_heal = (40.0 + type_heal_bonus + min(missing, heal_power) * 5.0) * w_heal
                        if score_heal > best_score:
                            best_score = score_heal
                            best_action = {
                                "type": "heal",
                                "unit": u_id,
                                "target": ally["id"],
                            }

        # ====================================================================
        # 3. Actions d'Attaque (Pawn, Warrior, Lancer, Archer) : Focus Fire
        # ====================================================================
        if attack_dmg > 0:
            # A. Attaquer les unités ennemies
            for enemy in enemy_units:
                e_id = enemy["id"]
                v_hp = virtual_enemy_hp.get(e_id, 0)
                if v_hp <= 0:
                    # Cible déjà détruite par nos attaques précédentes ce tour-ci (Règle d'or : ZERO gaspillage)
                    continue

                dist_e = _chebyshev(ux, uy, enemy["x"], enemy["y"])
                if dist_e <= reach:
                    # Score de base selon le type d'ennemi
                    e_type = enemy.get("type", "pawn")
                    type_priority = {
                        "monk": 45.0,
                        "archer": 40.0,
                        "lancer": 30.0,
                        "warrior": 25.0,
                        "pawn": 15.0,
                    }.get(e_type, 20.0)

                    # Bonus si l'attaque achève la cible (Règle d'or : éliminer une source de dégâts)
                    kill_bonus = 50.0 if v_hp <= attack_dmg else 0.0

                    # Focus Fire : achever les ennemis les plus entamés pour détruire le DPS adverse au plus vite
                    wounded_focus_bonus = max(0.0, (100.0 - v_hp) * 0.3)

                    # Bonus de proximité à notre château (défense)
                    castle_dist_bonus = 0.0
                    if my_castle:
                        dist_to_my_c = _dist_to_castle(enemy["x"], enemy["y"], my_castle)
                        if dist_to_my_c <= 5:
                            castle_dist_bonus = (6 - dist_to_my_c) * 10.0

                    score_attack = (type_priority + kill_bonus + wounded_focus_bonus + castle_dist_bonus) * w_attack

                    if score_attack > best_score:
                        best_score = score_attack
                        best_action = {
                            "type": "attack",
                            "unit": u_id,
                            "target": e_id,
                            "_target_type": "unit",
                            "_target_id": e_id,
                            "_dmg": attack_dmg,
                        }

            # B. Attaquer le château ennemi
            if enemy_castle and virtual_castle_hp > 0:
                dist_ec = _dist_to_castle(ux, uy, enemy_castle)
                if dist_ec <= reach:
                    finish_castle_bonus = 200.0 if virtual_castle_hp <= 200 else 0.0
                    is_assault = multipliers.get("move_assault", 1.0) >= 2.0
                    score_castle_atk = (1 + finish_castle_bonus) * w_attack
                    if score_castle_atk > best_score:
                        best_score = score_castle_atk
                        best_action = {
                            "type": "attack",
                            "unit": u_id,
                            "target": enemy_castle["id"],
                            "_target_type": "castle",
                            "_dmg": attack_dmg,
                        }

        # Appliquer l'action choisie et mettre à jour le tracker Focus Fire
        if best_action:
            if best_action.get("type") == "attack":
                if best_action.get("_target_type") == "unit":
                    t_id = best_action["_target_id"]
                    virtual_enemy_hp[t_id] = max(0, virtual_enemy_hp[t_id] - best_action["_dmg"])
                elif best_action.get("_target_type") == "castle":
                    virtual_castle_hp = max(0, virtual_castle_hp - best_action["_dmg"])

            # Nettoyer les champs internes
            clean_action = {k: v for k, v in best_action.items() if not k.startswith("_")}
            actions.append(clean_action)

    return actions
