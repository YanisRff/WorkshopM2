"""
opponents.py — Adversaires de test aux styles de jeu variés (Généralisation).

Permet de tester notre bot contre des stratégies radicalement différentes :
- rush: Rush ultra-agressif de Guerriers dès le début (peu d'économie, 100% agression).
- archer: Composition axée sur les Archers à distance (portée 4) avec barrage défensif.
- boom: Boom économique massif (6 pions) puis déferlement en milieu/fin de partie.
"""

import argparse
import json
import socket
import sys

import pathfinding
import micro
import economy

def play_archetype(game_id, team, archetype, host="127.0.0.1", port=5555):
    print(f"[{archetype.upper()}] Connexion en cours pour la partie {game_id} (team {team})...")
    with socket.create_connection((host, port)) as sock:
        f_in = sock.makefile("r", encoding="utf-8")
        f_out = sock.makefile("w", encoding="utf-8")

        def send(obj):
            f_out.write(json.dumps(obj) + "\n")
            f_out.flush()

        send({"type": "join", "game_id": game_id, "name": f"Bot-{archetype.capitalize()}", "team": team})

        rules = {}
        is_map_init = False

        for line in f_in:
            line = line.strip()
            if not line:
                continue
            msg = json.loads(line)
            mtype = msg.get("type")

            if mtype == "game_start":
                rules = msg.get("rules", {})
                print(f"[{archetype.upper()}] Match démarré.")

            elif mtype == "new_turn":
                state = msg["state"]
                if not is_map_init:
                    pathfinding.init_map(state, rules)
                    is_map_init = True

                # Déplacements selon l'archétype
                moves = compute_archetype_moves(state, rules, team, archetype)
                send({"type": "moves", "turn": msg["turn"], "moves": moves})

            elif mtype == "action":
                state = msg["state"]
                actions = compute_archetype_actions(state, rules, team, archetype)
                send({"type": "actions", "turn": msg["turn"], "actions": actions})

            elif mtype == "game_over":
                print(f"[{archetype.upper()}] Partie terminée. Vainqueur : {msg.get('winner')}")
                break

def compute_archetype_moves(state, rules, team, archetype):
    my_units = [u for u in state["units"] if u["team"] == team and u.get("hp", 0) > 0]
    enemies = [u for u in state["units"] if u["team"] != team and u.get("hp", 0) > 0]
    my_c = next((b for b in state["buildings"] if b["team"] == team), None)
    e_c = next((b for b in state["buildings"] if b["team"] != team), None)

    if not my_c or not e_c:
        return []

    c_pos = (my_c["x"], my_c["y"], my_c["width"], my_c["height"])
    ec_pos = (e_c["x"], e_c["y"], e_c["width"], e_c["height"])
    c_deposit = pathfinding.goal_field(state, pathfinding.cells_within(state, c_pos, 1))
    e_castle_field = pathfinding.goal_field(state, pathfinding.cells_within(state, ec_pos, 1))

    occupied = pathfinding.unit_positions(state)
    enemy_pos = pathfinding.unit_positions(state, enemy_of=team)
    moves = []

    gold_res = pathfinding.get_sorted_resources(state, team, "gold")
    meat_res = pathfinding.get_sorted_resources(state, team, "meat")

    for u in my_units:
        uid = u["id"]
        utype = u["type"]
        pos = (u["x"], u["y"])
        move_dist = rules.get("units", {}).get(utype, {}).get("move", 1)
        dest = pos

        if utype == "pawn":
            carrying = u.get("carrying")
            amount = carrying["amount"] if carrying else 0
            if amount >= 5 or (amount > 0 and pathfinding.dist_to_rect(pos, c_pos) <= 2):
                if c_deposit:
                    dest = pathfinding.step_toward(state, u, move_dist, c_deposit, enemy_pos, occupied)
            else:
                # Priorité selon l'archétype
                target_r = gold_res[0] if (uid % 2 == 0 and gold_res) else (meat_res[0] if meat_res else None)
                if target_r:
                    cells = pathfinding.cells_within(state, (target_r["pos"][0], target_r["pos"][1], 1, 1), 1)
                    if cells:
                        f = pathfinding.goal_field(state, cells)
                        dest = pathfinding.step_toward(state, u, move_dist, f, enemy_pos, occupied)
        else:
            # Combattants
            reach = rules.get("units", {}).get(utype, {}).get("range", 1)
            if archetype == "rush":
                # Fonce tête baissée sur le château adverse !
                if e_castle_field:
                    dest = pathfinding.step_toward(state, u, move_dist, e_castle_field, enemy_pos, occupied)
            elif archetype == "archer":
                # Archer : maintient une distance de 3-4 cases des ennemis les plus proches
                nearby_e = [e for e in enemies if pathfinding.get_distance_chebyshev(pos, (e["x"], e["y"])) <= 6]
                if nearby_e:
                    closest_e = sorted(nearby_e, key=lambda e: pathfinding.get_distance_chebyshev(pos, (e["x"], e["y"])))[0]
                    e_cells = pathfinding.cells_within(state, (closest_e["x"], closest_e["y"], 1, 1), reach)
                    if e_cells:
                        f = pathfinding.goal_field(state, e_cells)
                        dest = pathfinding.step_toward(state, u, move_dist, f, enemy_pos, occupied)
                elif e_castle_field:
                    dest = pathfinding.step_toward(state, u, move_dist, e_castle_field, enemy_pos, occupied)
            elif archetype == "robot":
                # Robot officiel : vague d'assaut à 6 combattants (guerriers / lanciers)
                assault_units = [m for m in my_units if m["type"] in ("warrior", "lancer")]
                dist_to_c = pathfinding.dist_to_rect(pos, c_pos)
                threats = [e for e in enemies if pathfinding.dist_to_rect((e["x"], e["y"]), c_pos) <= 10]
                nearby_e = [e for e in enemies if pathfinding.get_distance_chebyshev(pos, (e["x"], e["y"])) <= 5]

                if nearby_e:
                    t = sorted(nearby_e, key=lambda e: pathfinding.get_distance_chebyshev(pos, (e["x"], e["y"])))[0]
                    e_cells = pathfinding.cells_within(state, (t["x"], t["y"], 1, 1), reach)
                    if e_cells:
                        dest = pathfinding.step_toward(state, u, move_dist, pathfinding.goal_field(state, e_cells), enemy_pos, occupied)
                elif threats and (utype == "archer" or dist_to_c <= 15):
                    t = sorted(threats, key=lambda e: pathfinding.dist_to_rect((e["x"], e["y"]), c_pos))[0]
                    e_cells = pathfinding.cells_within(state, (t["x"], t["y"], 1, 1), reach)
                    if e_cells:
                        dest = pathfinding.step_toward(state, u, move_dist, pathfinding.goal_field(state, e_cells), enemy_pos, occupied)
                elif len(assault_units) >= 6 and utype in ("warrior", "lancer") and e_castle_field:
                    dest = pathfinding.step_toward(state, u, move_dist, e_castle_field, enemy_pos, occupied)
                elif utype in ("warrior", "lancer"):
                    rally_cells = pathfinding.cells_within(state, c_pos, 3)
                    if rally_cells:
                        dest = pathfinding.step_toward(state, u, move_dist, pathfinding.goal_field(state, rally_cells), enemy_pos, occupied)
            else:
                # Boom : défend jusqu'à avoir 6 combattants, puis attaque
                mil_count = sum(1 for m in my_units if m["type"] != "pawn")
                if mil_count >= 5 and e_castle_field:
                    dest = pathfinding.step_toward(state, u, move_dist, e_castle_field, enemy_pos, occupied)
                elif enemies:
                    closest_e = sorted(enemies, key=lambda e: pathfinding.dist_to_rect((e["x"], e["y"]), c_pos))[0]
                    e_cells = pathfinding.cells_within(state, (closest_e["x"], closest_e["y"], 1, 1), reach)
                    if e_cells:
                        f = pathfinding.goal_field(state, e_cells)
                        dest = pathfinding.step_toward(state, u, move_dist, f, enemy_pos, occupied)

        if dest != pos:
            occupied.discard(pos)
            occupied.add(dest)
            moves.append(pathfinding.move_order(uid, dest))

    return moves

def compute_archetype_actions(state, rules, team, archetype):
    my_c = next((b for b in state["buildings"] if b["team"] == team), None)
    bank = state["teams"][team]["resources"]
    next_meat = state["teams"][team]["next_meat_cost"]
    my_units = [u for u in state["units"] if u["team"] == team and u.get("hp", 0) > 0]
    pawn_count = sum(1 for u in my_units if u["type"] == "pawn")

    # Micro standard
    unit_actions = micro.generate_and_score_actions(state, rules, team, {"attack": 3.0, "heal": 2.0, "gather": 1.5, "deposit": 2.0})

    eco_actions = []
    # Recrutement selon l'archétype
    target_unit = None
    if archetype == "rush":
        # Max 2 pions, puis QUE du Guerrier rapide
        if pawn_count < 2:
            target_unit = "pawn"
        elif bank["gold"] >= 5 and bank["meat"] >= next_meat:
            target_unit = "warrior"
    elif archetype == "archer":
        # Max 3 pions, puis Archers et Guerriers protecteurs
        if pawn_count < 3:
            target_unit = "pawn"
        elif bank["gold"] >= 10 and bank["meat"] >= next_meat:
            target_unit = "archer"
        elif bank["gold"] >= 5 and bank["meat"] >= next_meat:
            target_unit = "warrior"
    elif archetype == "robot":
        # Robot officiel
        warrior_count = sum(1 for u in my_units if u["type"] == "warrior")
        lancer_count = sum(1 for u in my_units if u["type"] == "lancer")
        archer_count = sum(1 for u in my_units if u["type"] == "archer")
        threats = [e for e in state["units"] if e["team"] != team and my_c and pathfinding.dist_to_rect((e["x"], e["y"]), (my_c["x"], my_c["y"], my_c["width"], my_c["height"])) <= 10]

        army = "lancer" if lancer_count * 2 < warrior_count else "warrior"
        if archer_count < 3 and archer_count * 3 < (warrior_count + lancer_count):
            army = "archer"

        if threats:
            wishes = [army, "warrior", "archer"]
        elif pawn_count < 4:
            wishes = ["pawn"]
        elif pawn_count < 8 and pawn_count <= (warrior_count + lancer_count) + 4:
            wishes = ["pawn", army, "warrior"]
        else:
            wishes = [army, "warrior"]

        for w in wishes:
            cost_g = {"pawn": 1, "warrior": 5, "archer": 10, "lancer": 10, "monk": 15}.get(w, 1)
            if bank["gold"] >= cost_g and bank["meat"] >= next_meat:
                target_unit = w
                break

        if my_c and bank.get("wood", 0) > 0:
            missing_hp = my_c["max_hp"] - my_c["hp"]
            if bank["wood"] >= missing_hp or my_c["hp"] * 2 <= my_c["max_hp"]:
                eco_actions.append({"type": "repair", "building": my_c["id"]})
    else:  # Boom
        # Max 6 pions pour exploser l'économie !
        if pawn_count < 6:
            target_unit = "pawn"
        elif bank["gold"] >= 10 and bank["meat"] >= next_meat:
            target_unit = "lancer"
        elif bank["gold"] >= 5 and bank["meat"] >= next_meat:
            target_unit = "warrior"

    if my_c and target_unit:
        cost_g = {"pawn": 1, "warrior": 5, "archer": 10, "lancer": 10, "monk": 15}.get(target_unit, 1)
        if bank["gold"] >= cost_g and bank["meat"] >= next_meat:
            eco_actions.append({"type": "recruit", "building": my_c["id"], "unit_type": target_unit})

    all_actions = unit_actions + eco_actions
    return economy.sort_actions(all_actions)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("game_id")
    parser.add_argument("--team", required=True)
    parser.add_argument("--archetype", choices=("rush", "archer", "boom", "robot"), default="rush")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5555)
    args = parser.parse_args()

    play_archetype(args.game_id, args.team, args.archetype, args.host, args.port)
