#!/usr/bin/env python3
"""
robot_bot.py — Robot adversaire officiel du jeu (implémentation native Linux).

Permet de lancer le mode "Jouer contre un robot" du jeu :
    python robot_bot.py <game_id> --team yellow
"""

import argparse
import sys
from opponents import play_archetype

def main():
    parser = argparse.ArgumentParser(description="Robot adversaire officiel")
    parser.add_argument("game_id", help="Identifiant de la partie")
    parser.add_argument("--name", default="Robot")
    parser.add_argument("--team", choices=("purple", "yellow"), default="yellow")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5555)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    play_archetype(args.game_id, args.team, "robot", host=args.host, port=args.port)

if __name__ == "__main__":
    main()
