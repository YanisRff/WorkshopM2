def analyze_state(state, rules, team):
    """
    Analyse l'état global et renvoie un état stratégique (ex: 'DEVELOPPEMENT')
    """
    return 'DEVELOPPEMENT'

def get_multipliers(macro_state):
    """
    Renvoie les poids des actions selon l'état stratégique
    """
    return {
        'attack': 1.0,
        'gather_wood': 1.0,
        'gather_gold': 1.0,
        'gather_meat': 1.0,
        'heal': 1.0
    }
