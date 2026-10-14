UNIT_GOLD_COSTS = {
    'Pawn': 1,
    'Warrior': 5,
    'Lancer': 10,
    'Archer': 10,
    'Monk': 15
}

def get_virtual_bank(current_gold, current_meat, current_wood, planned_actions, team_units):
    """
    Calcule les ressources disponibles au moment exact où le château agira,
    en ajoutant les ressources des 'deposit' prévus ce tour-ci par le Tacticien.
    
    :param planned_actions: Liste des actions décidées (ex: [{"type": "deposit", "unit_id": 4}, ...])
    :param team_units: Dict des unités alliées (clé = unit_id) pour lire ce qu'elles transportent.
    """
    v_gold = current_gold
    v_meat = current_meat
    v_wood = current_wood
    
    for action in planned_actions:
        if action.get("type") == "deposit":
            unit_id = action.get("unit", action.get("unit_id"))
            unit = team_units.get(unit_id)
            if unit:
                # Structure réelle du protocole : unit['carrying'] = {'resource': 'gold', 'amount': 5}
                carrying = unit.get("carrying")
                if carrying and isinstance(carrying, dict):
                    res = carrying.get("resource")
                    amt = carrying.get("amount", 0)
                    if res == "gold":
                        v_gold += amt
                    elif res == "meat":
                        v_meat += amt
                    elif res == "wood":
                        v_wood += amt
                # Structure mockée pour compatibilité avec test_economy.py
                elif "inventory" in unit and isinstance(unit["inventory"], dict):
                    v_gold += unit["inventory"].get("gold", 0)
                    v_meat += unit["inventory"].get("meat", 0)
                    v_wood += unit["inventory"].get("wood", 0)
                
    return v_gold, v_meat, v_wood

def get_castle_action(gold, meat, wood, castle_hp, castle_max_hp, next_meat_cost, target_unit):
    """
    Gère la décision du château (1 action max par tour) : 'recruit' ou 'repair'.
    Il est recommandé de passer les ressources virtuelles (calculées après deposit) à cette fonction.
    
    :param target_unit: L'unité demandée par Le Général (ex: 'Archer', 'Pawn', ou None).
    """
    
    # --- 1. Règle de réparation (Repair) ---
    # Ne réparer que si notre stock de bois est inférieur ou égal aux PV manquants (zéro gaspillage).
    missing_hp = castle_max_hp - castle_hp
    if wood > 0 and wood <= missing_hp:
        return {"type": "repair"}

    # --- 2. Règle de recrutement (Recruit) ---
    # On essaie de recruter l'unité demandée par Le Général
    if target_unit and target_unit in UNIT_GOLD_COSTS:
        gold_cost = UNIT_GOLD_COSTS[target_unit]
        # On vérifie qu'on a bien les moyens (au cas où le Général aurait fait une erreur d'estimation)
        if gold >= gold_cost and meat >= next_meat_cost:
            return {
                "type": "recruit",
                "unit": target_unit
            }

    # Si on ne peut pas recruter l'unité demandée (ou si aucune n'est demandée),
    # on applique l'épargne stricte (on attend sans rien faire).
    return None

def sort_actions_for_server(actions_list):
    """
    Trie la liste des actions générées ce tour-ci pour respecter l'ordre strict du serveur :
    1. 'deposit' (les ressources rentrent en banque)
    2. 'recruit' / 'repair' (on utilise les ressources en banque)
    3. Autres actions (move, attack, gather, heal...)
    """
    def get_action_priority(action):
        action_type = action.get("type", "")
        if action_type == "deposit":
            return 0
        elif action_type in ["recruit", "repair"]:
            return 1
        else:
            return 2

    return sorted(actions_list, key=get_action_priority)

# Alias pour compatibilité avec bot.py
sort_actions = sort_actions_for_server

def get_economy_actions(state, rules, team, macro_state, planned_actions=None):
    """
    Génère les actions économiques du château (recruit et repair) selon l'état macro.
    Retourne une liste d'actions au format attendu par le serveur.
    """
    castle = next((b for b in state.get("buildings", []) if b["team"] == team and b["type"] == "castle"), None)
    if not castle or castle.get("hp", 0) <= 0:
        return []

    team_data = state["teams"][team]
    bank = team_data["resources"]
    gold = bank["gold"]
    meat = bank["meat"]
    wood = bank["wood"]
    next_meat_cost = team_data["next_meat_cost"]

    # Si des actions de dépôt sont prévues, calculer la banque virtuelle
    if planned_actions:
        team_units = {u["id"]: u for u in state["units"] if u["team"] == team}
        gold, meat, wood = get_virtual_bank(gold, meat, wood, planned_actions, team_units)

    castle_hp = castle["hp"]
    castle_max_hp = castle["max_hp"]
    actions = []

    # 1. Réparation (Zéro gaspillage : uniquement sur le stock réel en banque)
    real_wood = bank.get("wood", 0)
    missing_hp = castle_max_hp - castle_hp
    if real_wood > 0 and real_wood <= missing_hp:
        actions.append({"type": "repair", "building": castle["id"]})

    # 2. Recrutement
    my_units = [u for u in state.get("units", []) if u["team"] == team]
    unit_count = len(my_units)
    max_units = rules.get("max_units", 40) if rules else 40

    if unit_count < max_units:
        pawn_count = sum(1 for u in my_units if u["type"] == "pawn")
        lancer_count = sum(1 for u in my_units if u["type"] == "lancer")
        monk_count = sum(1 for u in my_units if u["type"] == "monk")
        warrior_count = sum(1 for u in my_units if u["type"] == "warrior")
        archer_count = sum(1 for u in my_units if u["type"] == "archer")
        target_unit = None

        if pawn_count < 3:
            target_unit = "pawn"
        elif macro_state == "DEFENSE_URGENTE":
            # Urgence absolue : si on ne peut pas payer un Lancier, prendre un Guerrier pour faire barrage
            if lancer_count >= 2 and monk_count == 0 and gold >= 15 and meat >= next_meat_cost:
                target_unit = "monk"
            elif gold >= 10 and meat >= next_meat_cost:
                target_unit = "lancer"
            elif gold >= 5 and meat >= next_meat_cost:
                target_unit = "warrior"
            elif pawn_count < 5 and gold >= 1 and meat >= next_meat_cost:
                target_unit = "pawn"
        elif pawn_count < 10:
            # 5 pions pour un flux optimal : 2 sur l'or (10/voyage), 3 sur la viande (15/voyage)
            target_unit = "pawn"
        else:
            # Composition d'élite (Lanciers 90 PV + Moines soigneurs) : pas de dilution avec des guerriers fragiles
            want_pawn = (lancer_count >= 2 and pawn_count <= 10 + lancer_count - 1)
            want_monk = (lancer_count >= 2 and monk_count == 0) or (lancer_count >= 5 and monk_count < 2) or (lancer_count >= 7 and monk_count < 3)
            if want_pawn:
                target_unit = "pawn"
            elif want_monk:
                target_unit = "monk"
            else:
                target_unit = "lancer"

        # Coût en or
        if target_unit:
            unit_cost = UNIT_GOLD_COSTS.get(target_unit.capitalize(), 1)
            if gold >= unit_cost and meat >= next_meat_cost:
                actions.append({
                    "type": "recruit",
                    "building": castle["id"],
                    "unit_type": target_unit
                })

    return actions
