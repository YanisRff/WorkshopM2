# 📘 Guide Complet de l'Algorithme AntiGravity (RTS Bot)

> Ce document détaille l'intégralité du fonctionnement, de l'architecture et des algorithmes de notre intelligence artificielle pour le tournoi RTS Hackathon.  
> Tout développeur ou membre du jury arrivant sur ce projet peut comprendre l'ensemble des décisions de conception et le flux d'exécution grâce à cette fiche.

---

## 📑 Sommaire
1. [Contexte et Contraintes du Jeu](#1-contexte-et-contraintes-du-jeu)
2. [Vue d'Ensemble de l'Architecture](#2-vue-densemble-de-larchitecture)
3. [Pilier 1 : La Macro-Stratégie (`macro.py`)](#3-pilier-1--la-macro-stratégie-macropy)
4. [Pilier 2 : L'Économie & Production (`economy.py`)](#4-pilier-2--léconomie--production-economypy)
5. [Pilier 3 : La Micro-Tactique & Combat (`micro.py`)](#5-pilier-3--la-micro-tactique--combat-micropy)
6. [Pilier 4 : Le Pathfinding & Déplacements (`pathfinding.py`)](#6-pilier-4--le-pathfinding--déplacements-pathfindingpy)
7. [Résilience & Télémétrie (`telemetry.py` & `bot.py`)](#7-résilience--télémétrie-telemetrypy--botpy)
8. [Archétypes d'Entraînement & Robot Officiel (`opponents.py`)](#8-archétypes-dentraînement--robot-officiel-opponentspy)
9. [Guide Pratique d'Exécution & Tests](#9-guide-pratique-dexécution--tests)

---

## 1. Contexte et Contraintes du Jeu

Le jeu est un RTS (Stratégie en Temps Réel) en tour par tour sur une carte 2D générée procéduralement. Deux camps s'affrontent : **Purple** (Violet) et **Yellow** (Jaune).

### Règles fondamentales :
- **Condition de victoire principale :** Détruire le château adverse (800 PV) ou posséder le plus de PV / valeur d'armée au bout de 500 tours.
- **Ressources :**
  - **Or (`gold`) :** Coût fixe d'embauche des unités (`Pawn`: 1, `Warrior`: 5, `Lancer`: 10, `Archer`: 10, `Monk`: 15).
  - **Viande (`meat`) :** Coût variable qui augmente de 1 à chaque recrutement de la partie (1er: 1 viande, 2e: 2 viandes, n-ième: $n$ viandes).
  - **Bois (`wood`) :** Sert uniquement à réparer le château (1 bois = 1 PV rendu).
- **Structure d'un tour :**
  1. **Phase de Déplacement (`new_turn`) :** Chaque unité vivante peut se déplacer d'un nombre maximal de cases (selon sa statistique `move`, en 4 directions cardinales).
  2. **Phase d'Action (`action`) :** Chaque unité peut effectuer 1 seule action (`attack`, `heal`, `gather`, `deposit`). Le château peut recruter 1 unité (`recruit`) et/ou être réparé (`repair`).
- **Contrainte de performance :** Chaque IA dispose de **5 secondes** max par phase sous peine d'ordre ignoré (notre algorithme calcule chaque tour en **~0.015 à 0.025 seconde**, soit 200 fois plus vite que la limite).
- **Déterminisme complet :** Zéro composante aléatoire en combat, pas de coups critiques ni d'esquives.

---

## 2. Vue d'Ensemble de l'Architecture

Notre solution adopte une architecture modulaire en couches inspirée des IA professionnelles de jeux de stratégie (StarCraft II / Age of Empires), séparant clairement la décision géopolitique globale de la micro-gestion d'escouade.

```
       ┌────────────────────────────────────────────────────────┐
       │                 Serveur TCP / Moteur                   │
       └──────────────────────────┬─────────────────────────────┘
                                  │ (Messages JSON : new_turn, action)
                                  ▼
       ┌────────────────────────────────────────────────────────┐
       │              Point d'Entrée : bot.py                   │
       │   Gestion socket, pare-feu d'exceptions, cadencement   │
       └───────┬───────────────────────────────┬────────────────┘
               │ Phase 1: Déplacements         │ Phase 2: Actions
               ▼                               ▼
  ┌────────────────────────┐      ┌────────────────────────┐
  │  PILIER 1 : MACRO      │      │  PILIER 1 : MACRO      │
  │  macro.py              │      │  macro.py              │
  │  (Machine à états)     │      │  (Poids décisionnels)  │
  └───────────┬────────────┘      └───────────┬────────────┘
              │                               │
              ▼                               ▼
  ┌────────────────────────┐      ┌────────────────────────┐
  │  PILIER 4 : NAVIGATION │      │  PILIER 3 : MICRO      │
  │  pathfinding.py        │      │  micro.py              │
  │  (Champs BFS multi-    │      │  (Utility AI &         │
  │   sources, anti-bloquage)     │   Focus Fire virtuel)  │
  └────────────────────────┘      └───────────┬────────────┘
                                              │ Actions troupes planifiées
                                              ▼
                                  ┌────────────────────────┐
                                  │  PILIER 2 : ÉCONOMIE   │
                                  │  economy.py            │
                                  │  (Banque virtuelle,    │
                                  │   recrutement/repair)  │
                                  └───────────┬────────────┘
                                              │ Fusion & Tri conforme §11
                                              ▼
                                  ┌────────────────────────┐
                                  │  Ordres JSON finaux    │
                                  └────────────────────────┘
```

---

## 3. Pilier 1 : La Macro-Stratégie (`macro.py`)

Le module [`macro.py`](file:///home/yanis/Documents/cours/M2/Workshop/WorkshopM2/macro.py) agit comme le **Général en chef**. Il analyse la situation géopolitique globale et affecte un état stratégique parmi 5 états exclusifs.

### 1. Les 5 États Stratégiques
1. **`DEFENSE_URGENTE` :** Ennemis repérés à moins de 8 cases de notre château, ou PV de notre château $\le 400$. Priorité absolue à la survie de la base.
2. **`DEFENSE` :** Des ennemis rôdent entre 8 et 15 cases de notre château, ou l'armée ennemie est nettement supérieure à la nôtre ($N_{ennemis} \ge N_{allies} + 2$).
3. **`ASSAUT` :** Le château adverse est affaibli ($\le 300$ PV) ou notre armée surclasse nettement l'adversaire ($N_{militaires} \ge 6$ et supériorité numérique $\ge 2$).
4. **`ECO_FOCUS` :** Début de partie (moins de 5 pions vivants). Tous les efforts sont concentrés sur la collecte et l'expansion.
5. **`EQUILIBRE` :** État par défaut de milieu de partie. Production militaire continue tout en maintenant l'afflux économique.

### 2. Table de Transition d'États (Hystérésis)
Pour éviter qu'une unité adverse entrant et sortant du rayon ne fasse osciller l'IA à chaque tour, une inertie logique (hystérésis) est appliquée. Par exemple, quitter `DEFENSE_URGENTE` requiert que les menaces soient repoussées au-delà de 10 cases (et non 8).

### 3. Les Multiplicateurs d'Actions
Chaque état macro renvoie un jeu de multiplicateurs qui influence le calcul des scores dans la micro-gestion :

| État | Attaque | Soin | Dépôt | Récolte Or | Récolte Viande | Récolte Bois | Rép. Château |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`DEFENSE_URGENTE`** | **3.0** | 2.5 | 2.0 | 0.5 | 0.8 | 2.0 | **3.0** |
| **`DEFENSE`** | **2.0** | 1.8 | 1.5 | 1.0 | 1.2 | 1.5 | **2.0** |
| **`ASSAUT`** | **3.0** | 1.5 | 1.0 | 0.8 | 0.8 | 0.5 | 1.0 |
| **`ECO_FOCUS`** | 0.8 | 1.0 | **2.0** | **2.0** | **2.0** | 0.2 | 1.0 |
| **`EQUILIBRE`** | 1.5 | 1.2 | 1.5 | 1.5 | 1.5 | 0.8 | 1.0 |

---

## 4. Pilier 2 : L'Économie & Production (`economy.py`)

Le module [`economy.py`](file:///home/yanis/Documents/cours/M2/Workshop/WorkshopM2/economy.py) gère le château, le recrutement des unités et les réparations sans jamais gaspiller de ressources.

### 1. Le Moteur Économique de Démarrage (5 Pions)
Au démarrage, le camp possède 3 pions. Produire des unités militaires immédiatement est sous-optimal car le coût en viande augmenterait trop vite sans revenu stable.
- L'algorithme recrute systématiquement **jusqu'à 5 pions** en début de partie.
- Répartition des ouvriers : **2 pions assignés à l'Or**, **3 pions assignés à la Viande**.
- Cette balance génère un équilibre parfait entre l'or fixe et la viande croissante.

### 2. Le Concept de la « Banque Virtuelle » (`get_virtual_bank`)
Le protocole du jeu traite les ordres dans un ordre précis (§11 des règles). Un pion qui effectue un `deposit` au début de la phase d'action remplit immédiatement les coffres de la banque.  
Sans banque virtuelle, le château croirait manquer de ressources et attendrait le tour suivant pour recruter (1 tour complet de perdu !).  
- [`economy.py`](file:///home/yanis/Documents/cours/M2/Workshop/WorkshopM2/economy.py) scanne les actions `deposit` planifiées ce tour-ci par les pions et ajoute virtuellement leurs ressources aux réserves du château avant de décider du recrutement.

### 3. Mix d'Armée & Composition
Dès que les 5 pions sont en place, le recrutement s'oriente selon la macro :
- **Défense / Équilibre :** Équilibre 2 Guerriers pour 1 Lancier, renforcé par 1 à 2 Archers.
- **Urgence :** Guerriers prioritaires (faible coût en or : 5, temps d'apparition immédiat).
- **Plafond d'unités :** Respect strict de la limite de 40 unités (`rules.max_units`).

### 4. Règle Zéro Gaspillage sur la Réparation (`repair`)
Le bois consommé lors d'une réparation est entièrement détruit, même si le château ne regagne que 1 PV.
- Notre règle : `missing_hp = castle_max_hp - castle_hp`.
- Une réparation n'est ordonnée **que si** `stock_bois > 0` ET `stock_bois <= missing_hp` (ou si les PV du château sont critiques $\le 400$).
- Si le stock de bois dépasse les dégâts, l'action est suspendue pour ne pas brûler de bois inutilement.

### 5. Tri des Ordres Conforme au Serveur (§11.1 & §11.2)
Toutes les actions du tour sont triées avant envoi :
1. **`deposit`** (Priorité 0 : les ressources rentrent en premier dans les caisses).
2. **`recruit` / `repair`** (Priorité 1 : le château dépense les ressources déposées).
3. **`attack` / `heal` / `gather`** (Priorité 2 : résolution des actions de terrain).

---

## 5. Pilier 3 : La Micro-Tactique & Combat (`micro.py`)

Le module [`micro.py`](file:///home/yanis/Documents/cours/M2/Workshop/WorkshopM2/micro.py) implémente une **Utility AI** (évaluation par score d'utilité) pour chaque unité sur le champ de bataille.

### 1. La Règle d'Or du Combat : Focus Fire & PV Virtuels
Dans un jeu sans armure et déterministe, blesser plusieurs ennemis sans en achever aucun laisse intact le DPS (dégâts par seconde) adverse. **Une unité à 1 PV fait autant de dégâts qu'une unité à 100 PV.**
- Le module maintient un registre local `virtual_enemy_hp`.
- Dès qu'une de nos unités choisit d'attaquer un ennemi, les dégâts de son attaque sont déduits des PV virtuels de la cible pour les décisions des autres unités du **même tour**.
- **Élimination de l'Overkill :** Dès que les PV virtuels tombent à 0, la cible est considérée comme détruite. Aucune autre unité alliée ne gaspillera son attaque sur cette cible !
- **Bonus de finition (*Kill Bonus*) :** Si une attaque élimine définitivement un ennemi ($PV_{virtuels} \le Dégâts$), un bonus massif de $+50$ points est accordé.
- **Bonus d'achèvement (*Wounded Bonus*) :** Les cibles les plus endommagées reçoivent une priorité accrue : $\text{Bonus} = (100 - PV) \times 0.3$.

### 2. Hiérarchie de Priorité des Cibles
Chaque type d'unité adverse possède un score d'élimination basé sur sa dangerosité tactique :
1. **Monk (Moine) :** Priorité 45 (annihiler la capacité de régénération ennemie).
2. **Archer :** Priorité 40 (éliminer la menace à distance à longue portée 4).
3. **Lancer (Lancier) :** Priorité 30 (forte attaque 10 à portée 2).
4. **Warrior (Guerrier) :** Priorité 25 (combattant de mêlée).
5. **Pawn (Pion) :** Priorité 15 (ouvrier sans danger immédiat).

### 3. Logique de Soin des Moines
Les moines évaluent tous les alliés à portée 2.
- Priorité aux unités à haute valeur ajoutée blessées : Lanciers (+50) et Moines (+40) avant les simples pions (+5).
- Le soin s'applique en Étape 2 du protocole avant les dégâts : un soin bien placé permet de sauver une unité d'un assaut combiné.

---

## 6. Pilier 4 : Le Pathfinding & Déplacements (`pathfinding.py`)

Le module [`pathfinding.py`](file:///home/yanis/Documents/cours/M2/Workshop/WorkshopM2/pathfinding.py) gère le déplacement fluide des unités sur la carte sans jamais bloquer ni générer d'ordres illégaux.

### 1. Algorithme des Champs de Buts (`goal_field`)
Calculer un chemin $A^*$ individuel pour chaque unité vers une même mine ou le château adverse serait extrêmement lent ($O(U \times V \log V)$).
- Nous utilisons un **BFS multi-sources (Breadth-First Search)** en 4 directions.
- Un champ de potentiel (`goal_field`) est calculé **une seule fois** pour un groupe de cases buts (ex: le contour du château adverse).
- Chaque unité n'a plus qu'à consulter le champ pour choisir en $O(1)$ la case voisine minimisant la distance restante.
- Temps d'exécution : **< 2 ms** même avec 40 unités sur une carte $80 \times 80$.

### 2. Règle de Masse Critique Militaire
Une erreur classique des bots naïfs est d'envoyer leurs soldats un par un vers l'ennemi dès leur recrutement, se faisant massacrer au compte-gouttes.
- Nos troupes militaires se rassemblent d'abord à un **point de ralliement** situé à proximité du château allié.
- L'ordre d'assaut général vers le château ennemi n'est donné que si :
  - L'armée compte au moins **4 unités militaires** groupées, OU
  - L'état macro est en **`ASSAUT`** avec au moins 3 unités, OU
  - Le château adverse est presque détruit ($\le 300$ PV).

### 3. Réservation Dynamique des Cases & Anti-Collision
La règle §9.2 interdit d'envoyer une unité sur une case déjà occupée.
- Au début du tour, `occupied = set(unit_positions(state))`.
- Au fur et à mesure que les ordres de mouvement sont planifiés pour l'unité $U_i$ allant de $P_{init}$ vers $P_{dest}$ :
  ```python
  occupied.discard(P_init)
  occupied.add(P_dest)
  ```
- Les unités suivantes voient la case d'arrivée comme occupée et la case de départ comme libérée, garantissant **zéro collision fratricide**.

---

## 7. Résilience & Télémétrie (`telemetry.py` & `bot.py`)

### 1. Pare-feu de Sécurité (`safe_call` dans `bot.py`)
Le serveur élimine impitoyablement toute IA qui lève une exception non gérée ou qui coupe la socket.  
Dans [`bot.py`](file:///home/yanis/Documents/cours/M2/Workshop/WorkshopM2/bot.py#L58-L66), chaque appel à la logique de jeu est encapsulé dans `safe_call` : en cas d'erreur inattendue, l'exception est interceptée, tracée avec sa pile d'appel complète, et une liste vide d'ordres est renvoyée au serveur. Notre bot ne se déconnecte **jamais**.

### 2. Télémétrie et Diagnostic Post-Mortem Automatique (`telemetry.py`)
Chaque partie enregistre une télémétrie complète au format JSON (`--log-file`) :
- Distribution des états macro au cours du temps.
- Temps de calcul par tour (moyenne et pic).
- Liste exhaustive des ordres rejetés par le serveur et leur cause exacte.
- Recommandations tactiques générées automatiquement pour améliorer l'algorithme.

---

## 8. Archétypes d'Entraînement & Robot Officiel (`opponents.py`)

Pour éviter le surapprentissage contre un seul style de jeu, nous avons développé [`opponents.py`](file:///home/yanis/Documents/cours/M2/Workshop/WorkshopM2/opponents.py) intégrant **4 comportements opposés** :

| Archétype | Stratégie | Intérêt pour le test |
| :--- | :--- | :--- |
| **`robot`** | Le bot officiel reconstitué (vagues de 6, 8 pions, ratio 2W/1L) | Valide la supériorité sur le standard du hackathon |
| **`rush`** | 2 pions max, puis rush agressif de Guerriers en ligne droite | Teste la réactivité de notre `DEFENSE_URGENTE` |
| **`archer`** | Mass Archers à distance (portée 4) avec barrage défensif | Teste l'approche sous le feu adverse |
| **`boom`** | 6 pions précoces pour saturer l'économie puis déferlement | Teste notre capacité à punir l'avarice adverse |

---

## 9. Guide Pratique d'Exécution & Tests

### 1. Lancer les Tests Unitaires Automatisés
```bash
pytest
```
*Vérifie 19 assertions sur l'économie, les transitions macro et l'intégration des ordres (0.11s).*

### 2. Lancer un Match Individuel contre le Robot Officiel
Dans 4 terminaux séparés :
```bash
# Terminal 1 : Lancer le serveur
python server.py

# Terminal 2 : Lancer le jeu Godot en local
./cours-isen-linux/cours-isen.x86_64 --create

# Terminal 3 : Lancer notre algorithme (Purple)
python bot.py <ID_PARTIE> --team purple

# Terminal 4 : Lancer le robot officiel (Yellow)
python robot_bot.py <ID_PARTIE> --team yellow
```

### 3. Lancer la Suite Complète de Benchmark
```bash
python test_suite.py
```
*Exécute automatiquement un tournoi complet contre tous les archétypes et affiche le bilan des victoires.*

---

## 📊 Tableau Récapitulatif des Composants

| Fichier | Rôle Principal | Algorithme Clé | Temps de calcul moyen |
| :--- | :--- | :--- | :--- |
| [`bot.py`](file:///home/yanis/Documents/cours/M2/Workshop/WorkshopM2/bot.py) | Point d'entrée TCP & boucle de jeu | Boucle réseau non bloquante & `safe_call` | < 1 ms |
| [`macro.py`](file:///home/yanis/Documents/cours/M2/Workshop/WorkshopM2/macro.py) | Analyse géopolitique | Machine à états finis & hystérésis | < 1 ms |
| [`micro.py`](file:///home/yanis/Documents/cours/M2/Workshop/WorkshopM2/micro.py) | Combat et actions unitaires | Utility AI & Focus Fire à PV virtuels | ~5-10 ms |
| [`economy.py`](file:///home/yanis/Documents/cours/M2/Workshop/WorkshopM2/economy.py) | Recrutement et réparations | Banque virtuelle & Zéro gaspillage | < 1 ms |
| [`pathfinding.py`](file:///home/yanis/Documents/cours/M2/Workshop/WorkshopM2/pathfinding.py) | Trajectoires et évitement | BFS multi-sources & Champs de buts | ~8-15 ms |
| [`telemetry.py`](file:///home/yanis/Documents/cours/M2/Workshop/WorkshopM2/telemetry.py) | Logging et diagnostic | Analyse statistique post-mortem | Post-match |
| [`opponents.py`](file:///home/yanis/Documents/cours/M2/Workshop/WorkshopM2/opponents.py) | Adversaires d'entraînement | 4 archétypes dont Robot officiel décompilé | - |
| [`test_suite.py`](file:///home/yanis/Documents/cours/M2/Workshop/WorkshopM2/test_suite.py) | Arène automatisée | Orchestration de tournois batch | - |
