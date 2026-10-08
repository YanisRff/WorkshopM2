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
            unit_id = action.get("unit_id")
            unit = team_units.get(unit_id)
            if unit and 'inventory' in unit:
                # Structure supposée : unit['inventory'] = {'gold': X, 'meat': Y, 'wood': Z}
                v_gold += unit['inventory'].get('gold', 0)
                v_meat += unit['inventory'].get('meat', 0)
                v_wood += unit['inventory'].get('wood', 0)
                
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
