import argparse
import json
import socket
import traceback

import pathfinding
import macro
import micro
import economy

is_map_initialized = False

def compute_turn_moves(state, rules, team):
    global is_map_initialized
    if not is_map_initialized:
        pathfinding.init_map(state, rules)
        is_map_initialized = True
        
    return pathfinding.get_moves(state, rules, team)

def compute_turn_actions(state, rules, team):
    global previous_macro_state
    # 1. Macro : conserver la strategie pour stabiliser les transitions.
    macro_state = macro.analyze_state(
        state, rules, team, previous_state=previous_macro_state
    )
    previous_macro_state = macro_state
    multipliers = macro.get_multipliers(macro_state)
    
    # 2. Machine à États (Multiplicateurs)
    # TODO: Déterminer l'état (Développement, Guerre Éco, Défense, Réparation, Assaut)

    # 1. Macro
    macro_state = macro.analyze_state(state, rules, team)
    multipliers = macro.get_multipliers(macro_state)
    
    # 2. Micro (Troupes)
    unit_actions = micro.generate_and_score_actions(state, rules, team, multipliers)
    
    # 3. Economy (Château)
    eco_actions = economy.get_economy_actions(state, rules, team, macro_state)
    
    # Fusion et Tri
    all_actions = unit_actions + eco_actions
    final_actions = economy.sort_actions(all_actions)
    
    return final_actions

def play(game_id, name, host, port, wanted_team=None):
    global previous_macro_state
    previous_macro_state = None
    print(f"Connexion au serveur {host}:{port} pour la partie {game_id}...")
    with socket.create_connection((host, port)) as sock:
        # Utilisation de makefile pour simplifier la lecture ligne par ligne
        stream = sock.makefile("rw", encoding="utf-8", newline="\n")

        def send(message):
            stream.write(json.dumps(message) + "\n")
            stream.flush()

        def safe_call(function, *arguments):
            # Rattraper les exceptions pour ne pas se déconnecter et perdre la partie
            try:
                orders = function(*arguments)
                return orders if isinstance(orders, list) else []
            except Exception:
                traceback.print_exc()
                return []

        # Rejoindre la partie
        join = {"type": "join", "game_id": game_id, "name": name}
        if wanted_team:
            join["team"] = wanted_team
        send(join)

        team, rules = None, None
        
        # Boucle principale de réception des messages
        for line in stream:
            if not line.strip():
                continue
                
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = message.get("type")
            
            if msg_type == "joined":
                team = message["team"]
                print(f"Rejoint avec succès ! Équipe: {team}")
            
            elif msg_type == "game_start":
                rules = message["rules"]
                print("Partie commencée ! Règles reçues.")
            
            elif msg_type == "new_turn":
                # Phase de déplacements
                moves = safe_call(compute_turn_moves, message["state"], rules, team)
                send({"type": "moves", "turn": message["turn"], "moves": moves})
            
            elif msg_type == "action":
                # Phase d'actions
                actions = safe_call(compute_turn_actions, message["state"], rules, team)
                send({"type": "actions", "turn": message["turn"], "actions": actions})
            
            elif msg_type == "game_over":
                print(f"Partie terminée. Vainqueur: {message.get('winner')}, Raison: {message.get('reason')}")
                break
            
            elif msg_type == "error":
                print(f"[ERREUR SERVEUR] {message.get('message')}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bot IA - Hackathon")
    parser.add_argument("game_id", help="ID de la partie")
    parser.add_argument("--name", default="AntiGravityBot")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5555)
    parser.add_argument("--team", choices=("purple", "yellow"), default=None,
                        help="Équipe souhaitée")
    args = parser.parse_args()
    
    play(args.game_id, args.name, args.host, args.port, args.team)
