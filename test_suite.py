import json
import os
import queue
import re
import stat
import subprocess
import sys
import threading
import time

def ensure_executable(path):
    if os.path.exists(path):
        current_stat = os.stat(path)
        os.chmod(path, current_stat.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

def main():
    os.makedirs("logs", exist_ok=True)
    godot_binary = "./cours-isen.exe"
    ensure_executable(godot_binary)

    # Démarrage du serveur Python avec -u (unbuffered)
    server_proc = subprocess.Popen(
        [sys.executable, "-u", "server.py"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    time.sleep(1.5)
    if server_proc.poll() is not None:
        err = server_proc.stdout.read()
        print(f"Erreur critique : le serveur s'est arrêté prématurément :\n{err}")
        return

    # Scénarios de test variés pour tester la généralisation
    scenarios = [
        {"archetype": "robot", "matches": 2, "desc": "Robot Officiel Intégré (Stratégie standard des organisateurs)"},
        {"archetype": "rush", "matches": 2, "desc": "Rush agressif de Guerriers rapides"},
        {"archetype": "archer", "matches": 2, "desc": "Harcèlement à distance par Archers"},
        {"archetype": "boom", "matches": 2, "desc": "Boom économique massif (6 pions)"},
        {"archetype": "mirror", "matches": 2, "desc": "Match Miroir (Notre IA contre elle-même)"},
    ]

    total_stats = {
        "victories": 0,
        "defeats": 0,
        "draws": 0,
        "total_turns": 0,
        "by_archetype": {}
    }

    match_idx = 0
    total_planned = sum(s["matches"] for s in scenarios)

    print(f"\n=======================================================")
    print(f"   LANCEMENT DU BATCH DE GÉNÉRALISATION ({total_planned} MATCHS)")
    print(f"=======================================================")

    for sc in scenarios:
        arch = sc["archetype"]
        desc = sc["desc"]
        total_stats["by_archetype"][arch] = {"win": 0, "loss": 0, "draw": 0}

        print(f"\n>>> DÉBUT DE LA SÉRIE CONTRE [{arch.upper()}] : {desc} <<<")

        for m_num in range(sc["matches"]):
            match_idx += 1
            print(f"\n--- Match {match_idx}/{total_planned} vs {arch.upper()} (Manche {m_num+1}/{sc['matches']}) ---")

            game_id_queue = queue.Queue()
            godot_proc = subprocess.Popen(
                [godot_binary, "--headless", "--", "--create", "--turn-delay=0"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            def read_godot():
                for line in iter(godot_proc.stdout.readline, ''):
                    m = re.search(r"partie\s+([A-Z0-9]{6})", line, re.IGNORECASE)
                    if m:
                        game_id_queue.put(m.group(1))

            t_gdt = threading.Thread(target=read_godot, daemon=True)
            t_gdt.start()

            try:
                game_id = game_id_queue.get(timeout=10)
            except queue.Empty:
                print("Erreur : Impossible de récupérer l'ID de partie.")
                godot_proc.kill()
                continue

            log_purple = f"logs/suite_{match_idx}_{game_id}_purple.json"

            # Purple : Notre bot officiel
            bot_purple = subprocess.Popen(
                [sys.executable, "-u", "bot.py", game_id, "--team", "purple", "--name", "AntiGravityBot", "--log-file", log_purple],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            # Yellow : Adversaire selon l'archétype
            if arch == "mirror":
                bot_yellow = subprocess.Popen(
                    [sys.executable, "-u", "bot.py", game_id, "--team", "yellow", "--name", "Bot-Mirror"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )
            else:
                bot_yellow = subprocess.Popen(
                    [sys.executable, "-u", "opponents.py", game_id, "--team", "yellow", "--archetype", arch],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )

            winner = None

            def monitor_purple():
                nonlocal winner
                for line in iter(bot_purple.stdout.readline, ''):
                    clean = line.strip()
                    if "Partie terminée" in clean:
                        m = re.search(r"Vainqueur:\s*(\w+)", clean)
                        if m:
                            winner = m.group(1)
                    elif "[ERREUR SERVEUR]" in clean:
                        print(f"[Purple] {clean}")

            t_p = threading.Thread(target=monitor_purple, daemon=True)
            t_p.start()

            bot_purple.wait()
            bot_yellow.wait()
            godot_proc.kill()
            godot_proc.wait()

            # Analyse résultat
            if winner == "purple":
                total_stats["victories"] += 1
                total_stats["by_archetype"][arch]["win"] += 1
                res_str = "✅ VICTOIRE de notre Bot (Purple)"
            elif winner == "yellow":
                total_stats["defeats"] += 1
                total_stats["by_archetype"][arch]["loss"] += 1
                res_str = f"❌ Défaite contre {arch.upper()}"
            else:
                total_stats["draws"] += 1
                total_stats["by_archetype"][arch]["draw"] += 1
                res_str = "⚖️ Match Nul"

            # Lire les tours et rejets
            rejections = 0
            turns = 0
            if os.path.exists(log_purple):
                try:
                    with open(log_purple) as f:
                        data = json.load(f)
                    turns = data.get("total_turns", 0)
                    rejections = data.get("rejections_total", 0)
                    total_stats["total_turns"] += turns
                except:
                    pass

            print(f"Résultat : {res_str} en {turns} tours | Rejets serveur : {rejections}")
            time.sleep(0.5)

    server_proc.kill()
    server_proc.wait()

    print("\n=======================================================")
    print("         BILAN DE GÉNÉRALISATION GLOBAL")
    print("=======================================================")
    print(f"Total Matchs Disputés : {match_idx}")
    print(f"Victoires de Notre Bot: {total_stats['victories']} ({(total_stats['victories']/match_idx)*100:.1f}%)")
    print(f"Défaites              : {total_stats['defeats']} ({(total_stats['defeats']/match_idx)*100:.1f}%)")
    print(f"Matchs Nuls           : {total_stats['draws']} ({(total_stats['draws']/match_idx)*100:.1f}%)")
    if match_idx > 0:
        print(f"Durée moyenne         : {total_stats['total_turns']//match_idx} tours/partie")
    print("\nPerformance par style de jeu adverse :")
    for arch, st in total_stats["by_archetype"].items():
        total_a = st['win'] + st['loss'] + st['draw']
        win_pct = (st['win']/total_a)*100 if total_a > 0 else 0
        print(f"• vs {arch.upper():<7} : {st['win']}V - {st['loss']}D - {st['draw']}N ({win_pct:.0f}% win rate)")

if __name__ == "__main__":
    main()
