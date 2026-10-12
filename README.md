# ⚔️ RTS Hackathon AI — AntiGravity Bot

Agent autonome et intelligent pour le jeu de stratégie en temps réel (RTS) en tour par tour sur grille.

## 📖 Documentation Complète de l'Algorithme
👉 **Toute l'explication de l'algorithme, des choix d'architecture et des formules mathématiques est disponible dans la fiche détaillée :**  
📄 **[ALGORITHME.md](file:///home/yanis/Documents/cours/M2/Workshop/WorkshopM2/ALGORITHME.md)**

---

## 🚀 Démarrage Rapide

### 1. Lancer les tests unitaires
```bash
pytest
```

### 2. Lancer un match contre le Robot Officiel
```bash
# Dans des terminaux distincts :
python server.py
./cours-isen-linux/cours-isen.x86_64 --create
python bot.py <ID_PARTIE> --team purple
python robot_bot.py <ID_PARTIE> --team yellow
```

### 3. Lancer la suite de test multi-archétypes
```bash
python test_suite.py
```

---

## 🏛️ Architecture en Bref

- **[`bot.py`](file:///home/yanis/Documents/cours/M2/Workshop/WorkshopM2/bot.py)** : Orchestrateur réseau TCP, pare-feu anti-crash (`safe_call`).
- **[`macro.py`](file:///home/yanis/Documents/cours/M2/Workshop/WorkshopM2/macro.py)** : Machine à 5 états stratégiques (`ECO_FOCUS`, `EQUILIBRE`, `DEFENSE`, `DEFENSE_URGENTE`, `ASSAUT`).
- **[`economy.py`](file:///home/yanis/Documents/cours/M2/Workshop/WorkshopM2/economy.py)** : Moteur économique (5 pions), banque virtuelle, zéro gaspillage de bois/viande.
- **[`micro.py`](file:///home/yanis/Documents/cours/M2/Workshop/WorkshopM2/micro.py)** : Utility AI, *Focus Fire* avec tracking des PV virtuels, élimination de l'overkill.
- **[`pathfinding.py`](file:///home/yanis/Documents/cours/M2/Workshop/WorkshopM2/pathfinding.py)** : BFS multi-sources, champs de buts (`goal_field`), rassemblement en masse critique.
- **[`telemetry.py`](file:///home/yanis/Documents/cours/M2/Workshop/WorkshopM2/telemetry.py)** : Enregistrement des matchs et diagnostic post-mortem.
- **[`opponents.py`](file:///home/yanis/Documents/cours/M2/Workshop/WorkshopM2/opponents.py)** & **[`robot_bot.py`](file:///home/yanis/Documents/cours/M2/Workshop/WorkshopM2/robot_bot.py)** : Archétypes d'entraînement et bot officiel décompilé.