import argparse
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

def print_post_mortem(log_file, team_label):
    if not os.path.exists(log_file):
        return
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        print(f"\n--- Diagnostic Post-Mortem [{team_label}] ({data.get('result', '')}) ---")
        print(f"• Tours joués : {data.get('total_turns')}")
        print(f"• Répartition Macro : {data.get('macro_distribution')}")
        
        rejections = data.get("rejections_total", 0)
        if rejections > 0:
            print(f"• ⚠️ Ordres rejetés par le serveur : {rejections}")
            for reason, count in data.get("rejections_by_reason", {}).items():
                print(f"   - {count}x : {reason}")
        else:
            print("• ✅ Zéro ordre rejeté (100% légal)")

        recs = data.get("recommendations", [])
        if recs:
            print("• 💡 Recommandations tactiques :")
            for r in recs:
                print(f"   → {r}")
    except Exception as e:
        print(f"Erreur lors de la lecture du rapport : {e}")

def main():
    parser = argparse.ArgumentParser(description="Arène de simulation pour l'IA")
    parser.add_argument("num_matches", nargs="?", type=int, default=1, help="Nombre de parties à jouer (ex: python arena.py 5)")
    parser.add_argument("--team", choices=["purple", "yellow", "alternate"], default="purple",
                        help="Couleur de notre algorithme ('purple', 'yellow', ou 'alternate' pour alterner à chaque manche)")
    args = parser.parse_args()
    num_matches = args.num_matches

    os.makedirs("logs", exist_ok=True)
    godot_binary = "./cours-isen.exe"
    ensure_executable(godot_binary)
    ensure_executable("./cours-isen-linux/cours-isen.sh")

    print(f"Lancement de {num_matches} partie(s) avec enregistrement de télémétrie...")
    if args.team == "alternate":
        print("Mode d'assignation : Alternance (Purple aux manches impaires, Yellow aux manches paires)")
    else:
        print(f"Notre algorithme est configuré sur : {args.team.upper()}")

    # Démarrage du serveur Python avec -u (unbuffered)
    server_proc = subprocess.Popen(
        [sys.executable, "-u", "server.py"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    time.sleep(1.0)  # Laisse le temps au serveur d'ouvrir le port 5555

    results = {"purple": 0, "yellow": 0, "draw": 0}
    our_wins = 0
    our_losses = 0

    for i in range(num_matches):
        if args.team == "alternate":
            our_team = "purple" if i % 2 == 0 else "yellow"
        else:
            our_team = args.team
        opp_team = "yellow" if our_team == "purple" else "purple"

        our_color_name = "PURPLE (Violet)" if our_team == "purple" else "YELLOW (Jaune)"
        opp_color_name = "YELLOW (Jaune)" if our_team == "purple" else "PURPLE (Violet)"

        print(f"\n==========================================")
        print(f"            MATCH {i+1} / {num_matches}")
        print(f"==========================================")
        print(f"🎮 Notre algorithme  : {our_color_name}")
        print(f"🤖 Clone adverse     : {opp_color_name}")

        game_id_queue = queue.Queue()

        # Lancer Godot headless (mode 2 IA)
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

        # Attente de l'ID de partie
        try:
            game_id = game_id_queue.get(timeout=10)
            print(f"Partie créée avec l'ID : {game_id}")
        except queue.Empty:
            print("Erreur : Impossible de récupérer l'ID de partie depuis Godot.")
            godot_proc.kill()
            continue

        log_purple = f"logs/match_{game_id}_purple.json"
        log_yellow = f"logs/match_{game_id}_yellow.json"

        name_purple = "AntiGravityBot (Notre Algo)" if our_team == "purple" else "Clone-Adverse"
        name_yellow = "AntiGravityBot (Notre Algo)" if our_team == "yellow" else "Clone-Adverse"

        # Lancer le bot Purple
        bot_purple = subprocess.Popen(
            [sys.executable, "-u", "bots/bot4/bot.py", game_id, "--team", "purple", "--name", name_purple, "--log-file", log_purple],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        # Lancer le bot Yellow
        bot_yellow = subprocess.Popen(
            [sys.executable, "-u", "bot.py", game_id, "--team", "yellow", "--name", name_yellow, "--log-file", log_yellow],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        winner = None

        def monitor_bot(proc, label):
            nonlocal winner
            for line in iter(proc.stdout.readline, ''):
                clean = line.strip()
                if "Partie terminée" in clean:
                    print(f"[{label}] {clean}")
                    m = re.search(r"Vainqueur:\s*(\w+)", clean)
                    if m:
                        winner = m.group(1)
                elif "ERREUR" in clean or "[ERREUR SERVEUR]" in clean:
                    print(f"[{label}] {clean}")

        t_p = threading.Thread(target=monitor_bot, args=(bot_purple, "Purple"), daemon=True)
        t_y = threading.Thread(target=monitor_bot, args=(bot_yellow, "Yellow"), daemon=True)
        t_p.start()
        t_y.start()

        bot_purple.wait()
        bot_yellow.wait()

        # Fermer Godot à la fin de la partie
        godot_proc.kill()
        godot_proc.wait()

        if winner in results:
            results[winner] += 1

        if winner == our_team:
            verdict = f"✅ VICTOIRE de notre algorithme ({our_team.upper()}) !"
            our_wins += 1
        elif winner == opp_team:
            verdict = f"❌ DÉFAITE de notre algorithme ({our_team.upper()}) (Victoire de {opp_team.upper()})"
            our_losses += 1
        else:
            verdict = "🤝 MATCH NUL"

        print(f"\n🏆 Résultat final : Vainqueur = {winner.upper() if winner else 'INCONNU'}")
        print(f"👉 {verdict}")
        print(f"Score global : Purple {results['purple']} - {results['yellow']} Yellow | Nuls : {results['draw']}")

        # Analyse post-mortem du camp perdant
        if winner == "purple":
            tag = f"Notre Algorithme ({our_team.capitalize()}) [Perdant]" if our_team == "yellow" else "Clone-Adverse (Yellow) [Perdant]"
            print_post_mortem(log_yellow, tag)
        elif winner == "yellow":
            tag = f"Notre Algorithme ({our_team.capitalize()}) [Perdant]" if our_team == "purple" else "Clone-Adverse (Purple) [Perdant]"
            print_post_mortem(log_purple, tag)
        else:
            print_post_mortem(log_purple, f"Notre Algorithme ({our_team.capitalize()})")

        time.sleep(0.5)

    server_proc.kill()
    server_proc.wait()

    print("\n==========================================")
    print("               BILAN FINAL")
    print("==========================================")
    print(f"Total parties jouées          : {num_matches}")
    print(f"Victoires de Notre Algorithme : {our_wins} ({(our_wins/num_matches)*100:.1f}%)")
    print(f"Défaites de Notre Algorithme  : {our_losses} ({(our_losses/num_matches)*100:.1f}%)")
    print(f"Matchs nuls                   : {results['draw']} ({(results['draw']/num_matches)*100:.1f}%)")
    print(f"Détail par couleur            : Purple {results['purple']} ({(results['purple']/num_matches)*100:.1f}%) | Yellow {results['yellow']} ({(results['yellow']/num_matches)*100:.1f}%)")
    print("Fichiers de logs détaillés disponibles dans le dossier logs/\n")

if __name__ == "__main__":
    main()
