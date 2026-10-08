# Battez-vous ! — Règles complètes du jeu et du protocole

Ce document contient **tout** ce qu'il faut savoir pour écrire une IA (un algorithme ou un modèle) capable de jouer et de gagner.

> **Source de vérité.** Les valeurs numériques (points de vie, coûts, portées…) indiquées ici sont celles de la version actuelle. Elles peuvent être ajustées. La partie vous envoie toujours les valeurs réellement utilisées dans le champ `rules` du message `game_start` (voir [§13](#13-référence-des-messages)). **Une IA robuste lit `rules` au lieu de recopier les chiffres de ce document.**

---

## Sommaire

1. [Le jeu en bref](#1-le-jeu-en-bref)
2. [Lancer une partie et s'entraîner](#2-lancer-une-partie-et-sentraîner)
3. [Architecture et connexion](#3-architecture-et-connexion)
4. [La carte](#4-la-carte)
5. [Les ressources et l'économie](#5-les-ressources-et-léconomie)
6. [Les unités](#6-les-unités)
7. [Le château](#7-le-château)
8. [Déroulement d'un tour](#8-déroulement-dun-tour)
9. [Phase de déplacement](#9-phase-de-déplacement)
10. [Phase d'action](#10-phase-daction)
11. [Ordre de résolution et cas limites](#11-ordre-de-résolution-et-cas-limites)
12. [Fin de partie](#12-fin-de-partie)
13. [Référence des messages](#13-référence-des-messages)
14. [Référence de l'état (`state`)](#14-référence-de-létat-state)
15. [Référence des événements (`events`)](#15-référence-des-événements-events)
16. [Liste complète des refus (`rejected`)](#16-liste-complète-des-refus-rejected)
17. [Liste complète des erreurs serveur](#17-liste-complète-des-erreurs-serveur)
18. [Chiffres utiles](#18-chiffres-utiles)
19. [Le robot adversaire](#19-le-robot-adversaire)
20. [Fichiers fournis](#20-fichiers-fournis)
21. [Pièges fréquents et FAQ](#21-pièges-fréquents-et-faq)
22. [Glossaire français / anglais](#22-glossaire-français--anglais)

---

## 1. Le jeu en bref

- Deux camps s'affrontent : **purple** (violet) et **yellow** (jaune).
- Chaque camp possède un **château**. **Le but est de détruire le château adverse.**
- La partie se joue **au tour par tour**. Chaque tour comporte deux phases jouées **simultanément** par les deux camps :
  1. **déplacement** : chaque unité peut se déplacer ;
  2. **action** : chaque unité peut agir (attaquer, soigner, récolter, déposer) ; le château peut recruter une unité et être réparé.
- On récolte des ressources pour recruter des unités. Un recrutement coûte de l'**or** (fixe selon l'unité) et de la **viande** (de plus en plus cher à chaque recrutement). Le **bois** sert à **réparer le château**.
- **Le château est le seul bâtiment du jeu** : on ne construit rien, et c'est lui qui recrute toutes les unités.
- **L'information est complète** : il n'y a pas de brouillard de guerre. À chaque phase, vous recevez l'état entier de la partie, adversaire compris.
- **Vous ne contrôlez rien à la souris** : c'est votre programme qui joue. Le jeu Godot se contente d'appliquer les règles et d'afficher la partie.

---

## 2. Lancer une partie et s'entraîner

Trois programmes participent à une partie :

| Programme | Rôle | Commande |
|---|---|---|
| **Le serveur** (Python) | Crée les parties, génère la carte, relaie les messages, cadence les tours. | `py server/server.py` |
| **Le jeu** (Godot, `cours-isen.exe`) | Applique les règles et affiche la partie. Une fenêtre = une partie. | `cours-isen.exe` |
| **Les IA** (vos programmes) | Se connectent au serveur et jouent. | `py mon_ia.py ABC123` |

### 2.1 Étapes

1. Démarrer le serveur : `py server/server.py`. Il doit tourner **avant** le jeu.
2. Lancer le jeu et choisir un mode :
   - **Jouer contre un robot** : le serveur lance automatiquement le robot adversaire (voir [§19](#19-le-robot-adversaire)), qui prend le camp **yellow**. Vous ne connectez que votre IA, qui sera **purple**.
   - **Jouer contre un autre joueur / une autre IA** : deux IA doivent se connecter.
3. Cliquer sur **Créer une partie**. Un **ID de partie** de 6 caractères (par exemple `K3P9QZ`) s'affiche en haut de la fenêtre. Le bouton « Copier l'ID » le copie dans le presse-papier. L'ID apparaît aussi dans la console du serveur : `partie K3P9QZ creee`.
4. Lancer votre IA avec cet ID.
5. La partie démarre dès que les deux places sont prises.

### 2.2 Lancement automatique (entraînement)

Le jeu peut créer une partie sans passer par le menu. Les options se placent **après un `--`** :

```
cours-isen.exe -- --create
cours-isen.exe -- --create --robot --seed=42 --max-turns=500 --turn-delay=0
cours-isen.exe --headless -- --create --robot --turn-delay=0
```

| Option | Effet | Valeur par défaut |
|---|---|---|
| `--create` | Crée la partie immédiatement, sans le menu. | (menu) |
| `--robot` | Mode « contre un robot ». | mode deux IA |
| `--host=ADRESSE` | Adresse du serveur. | `127.0.0.1` |
| `--port=PORT` | Port du serveur. | `5555` |
| `--seed=N` | Graine de la carte : la même graine redonne la même carte. | aléatoire |
| `--max-turns=N` | Nombre maximum de tours. | `500` |
| `--turn-delay=S` | Pause d'affichage entre deux phases, en secondes. `0` = le plus rapide possible. | `0.5` |
| `--headless` (avant le `--`) | Aucune fenêtre : idéal pour enchaîner des matchs. | fenêtre |

### 2.3 Options du serveur

```
py server/server.py [--host 0.0.0.0] [--port 5555] [--timeout 5] [--max-turns 500] [-v]
```

| Option | Effet | Défaut |
|---|---|---|
| `--host` | Interface d'écoute. `0.0.0.0` = accepte les connexions des autres machines du réseau. | `0.0.0.0` |
| `--port` | Port TCP. | `5555` |
| `--timeout` | Temps (secondes) laissé à **chaque** IA pour répondre à **chaque** phase. | `5` |
| `--max-turns` | Limite de tours si la partie n'en précise pas. | `500` |
| `-v` | Journal détaillé. | non |

Le serveur peut héberger **plusieurs parties en parallèle** : chaque fenêtre du jeu crée sa propre partie avec son propre ID.

### 2.4 Lancer une IA

Avec le template fourni : `py clients/template_bot.py ABC123 --name mon-ia`.
Options communes aux IA fournies : `--name` (nom affiché, 32 caractères max), `--host`, `--port`, `--team purple|yellow` (camp souhaité, accordé s'il est libre).

---

## 3. Architecture et connexion

```
  IA purple ─┐                             ┌─ Jeu Godot : applique les règles, affiche
             ├── TCP ── serveur Python ── TCP ┤
  IA yellow ─┘   (cadence, relaie,          └─ (une instance du jeu par partie)
                  génère la carte)
```

- Le **serveur ne connaît pas les règles** : il transmet vos ordres au jeu, qui les valide et les applique, puis il vous renvoie le nouvel état.
- Vous ne parlez **qu'au serveur**.

### 3.1 Transport

- Connexion **TCP** à l'adresse et au port du serveur (par défaut `127.0.0.1:5555`).
- Chaque message, dans les deux sens, est **un objet JSON écrit sur une seule ligne**, encodé en **UTF-8** et **terminé par un retour à la ligne `\n`**.
- Chaque message possède un champ `"type"` qui indique sa nature.
- Les lignes vides sont ignorées.
- Une ligne qui n'est pas un objet JSON valide provoque un message `error` ; la connexion reste ouverte.
- Taille maximale d'une ligne : 16 Mo, très au-delà de ce qui est nécessaire (un état complet pèse quelques dizaines de Ko).
- Pensez à **vider le tampon d'écriture** (`flush`) après chaque message, sinon le serveur ne le reçoit pas.

### 3.2 Cycle de vie d'une connexion d'IA

1. Ouvrir la connexion.
2. Envoyer `join` avec l'ID de la partie.
3. Recevoir `joined` (votre camp), puis attendre `game_start` (les règles et l'état initial).
4. Répondre à chaque `new_turn` par `moves`, et à chaque `action` par `actions`.
5. Recevoir `game_over`. Le serveur ferme alors la connexion.

Un exemple d'échange complet se trouve en [§13.4](#134-exemple-déchange-complet).

---

## 4. La carte

### 4.1 Coordonnées

- La carte est une grille de `width` × `height` cases.
- `x` est la colonne : il va de `0` (gauche) à `width - 1` (droite).
- `y` est la ligne : il va de `0` (haut) à `height - 1` (bas). **L'axe `y` pointe vers le bas.**
- La grille s'indexe **`grid[y][x]`** : la ligne d'abord, puis la colonne.
- Une position s'écrit toujours sous la forme d'une liste **`[x, y]`** dans les ordres et les événements, et sous la forme de deux champs `"x"` et `"y"` dans l'état.
- Les coordonnées doivent être des **entiers positifs ou nuls**. Une coordonnée à virgule est tronquée (`3.7` devient `3`) : évitez-le.

### 4.2 Codes de terrain

Chaque case de `grid` contient un entier. Son nom est donné par `rules.legend[code]`.

| Code | Nom (`legend`) | Description | Marchable |
|---|---|---|---|
| 0 | `water` | Eau (mer et lacs). | non |
| 1 | `ground` | Herbe nue. | **oui** |
| 2 | `rock` | Rocher. | non |
| 3 | `gold` | Mine d'or (ressource). | **non** |
| 4 | `tree` | Arbre (ressource : bois). | **oui** |
| 5 | `sheep` | Mouton (ressource : viande). | **oui** |
| 6 | `castle_purple` | Château violet. | non |
| 7 | `castle_yellow` | Château jaune. | non |

Il n'existe aucun autre code : la grille ne contient que ces 8 valeurs.

- **Marchable** : une unité peut traverser cette case et s'y arrêter. La liste est aussi dans `rules.walkable` : `["ground", "tree", "sheep"]`.
- **Attention** : on peut marcher sur un arbre ou un mouton, mais **pas** sur une mine d'or.
- Un château occupe 4 × 2 cases, qui portent toutes son code.
- La seule évolution possible de la grille pendant la partie : un château détruit redevient `ground` (ce qui termine la partie). Les gisements ne changent jamais : ils sont inépuisables (voir [§5.1](#51-les-trois-ressources)).
- **Les unités n'apparaissent pas dans `grid`** : leurs positions sont dans la liste `units`.

### 4.3 Forme et génération de la carte

La carte est générée aléatoirement par le serveur. Chaque partie a une graine (`seed`), et la même graine redonne la même carte.

- **Taille** : une île de 40 à 50 cases de large et de haut, entourée d'un anneau d'eau de 15 cases. La carte mesure donc entre **70 et 80 cases** de large et de haut. Largeur et hauteur sont tirées indépendamment.
- **Côtes** : le littoral est irrégulier et grignote jusqu'à 6 cases sur les bords de l'île.
- **Lacs** : 2 à 4 petits lacs (rayon 2 à 3), chacun doublé par symétrie.
- **Symétrie centrale** : la carte est parfaitement équitable. La case `(x, y)` a pour miroir la case `(width - 1 - x, height - 1 - y)`, et les deux portent le même terrain (au camp près pour les châteaux).
- **Châteaux** (4 × 2 cases) :
  - le château **purple** est dans le **quart nord-ouest** : son coin haut-gauche a des coordonnées `x` et `y` comprises entre 25 et 29 ;
  - le château **yellow** est son miroir, dans le **quart sud-est** ;
  - autour de chaque château, un anneau de **3 cases** est garanti en herbe nue.
- **Rochers** : 10 à 20 rochers par moitié (20 à 40 en tout), espacés d'au moins 5 cases autant que possible.
- **Ressources** : 5 à 7 gisements **de chaque type** par moitié de carte, soit 10 à 14 mines d'or, 10 à 14 arbres et 10 à 14 moutons en tout. Ils sont espacés d'au moins 3 cases autant que possible, et ne sont jamais posés sur la case centrale.
- **Accessibilité** : toute la terre restante est accessible à pied depuis les châteaux. Les recoins isolés sont transformés en eau à la génération, et chaque gisement est donc atteignable.
- **Distance entre les châteaux** (mesurée sur 300 cartes) : entre **9 et 27 cases** en distance de Chebyshev (médiane 19). À pied, il faut entre **14 et 45 pas** (médiane 30) pour aller des abords d'un château aux abords de l'autre. Certaines cartes sont donc beaucoup plus « serrées » que d'autres.

### 4.4 Distances

Deux notions de distance coexistent dans le jeu, et il est important de ne pas les confondre.

1. **Portée (attaque, soin, récolte, dépôt)** : c'est la **distance de Chebyshev**, `max(|x1 - x2|, |y1 - y2|)`. Les diagonales comptent pour 1. Les 8 cases autour d'une unité sont donc à distance 1.
   - Pour un **château** (plusieurs cases), on mesure jusqu'à **sa case la plus proche**.
   - « À 1 case » veut donc dire : sur l'une des 8 cases voisines, ou sur la case elle-même.
2. **Déplacement** : une unité se déplace **case par case, en 4 directions seulement** (haut, bas, gauche, droite, sans diagonale). Le nombre de pas est la longueur du chemin réellement parcouru, en contournant les obstacles.

Exemple : une unité en `[10, 10]` est à distance de Chebyshev 1 de `[11, 11]`, mais il lui faut 2 pas pour s'y rendre.

---

## 5. Les ressources et l'économie

### 5.1 Les trois ressources

| Ressource (`resource`) | Gisement (terrain) | Marchable |
|---|---|---|
| `gold` (or) | `gold` (mine d'or) | non |
| `wood` (bois) | `tree` (arbre) | oui |
| `meat` (viande) | `sheep` (mouton) | oui |

- Les gisements sont **inépuisables** : on peut y récolter indéfiniment, ils ne disparaissent jamais et ne bougent jamais. Leur position, connue dès le début de la partie, reste valable jusqu'à la fin.
- Il n'y a donc pas de pénurie globale : ce qui limite l'économie, c'est le **nombre de pions** et la **distance** entre les gisements et le château.
- Les gisements sont partagés entre les deux camps : rien n'empêche d'aller exploiter ceux du côté adverse.
- Un même gisement peut être exploité par autant de pions que l'on veut, en même temps.

### 5.2 Stocks de départ

Chaque camp commence avec des stocks **entièrement vides : 0 or, 0 bois, 0 viande** (`rules.start_resources`).

Comme tout recrutement coûte au moins 1 or et 1 viande, **aucun recrutement n'est possible avant d'avoir récolté et déposé au moins 1 or et 1 viande**. Le début de partie se joue donc uniquement avec les 3 pions de départ.

### 5.3 À quoi servent les ressources

| Ressource | Utilité |
|---|---|
| `gold` (or) | Part fixe du coût de chaque unité (voir [§6.2](#62-coût-de-recrutement)). |
| `meat` (viande) | Part variable du coût de chaque unité, qui augmente à chaque recrutement. |
| `wood` (bois) | **Réparer le château** avec l'action `repair` : 1 bois = 1 PV, et **tout** le stock de bois est consommé à chaque réparation (voir [§10.7](#107-repair--réparer-le-château)). |

### 5.4 Le cycle de récolte

1. Un **pion** se place **à 1 case** d'un gisement (sur une case voisine, diagonales comprises, ou sur le gisement lui-même s'il est marchable).
2. Action `gather` : le pion prélève **1 unité** (`rules.gather_amount`). Les ressources se récoltent donc **une par une**, une par action. Le gisement, lui, ne diminue pas.
3. Un pion transporte **au maximum 5 unités à la fois** (`rules.carry_capacity`), d'**un seul type** de ressource. Il faut donc 5 récoltes, soit 5 tours, pour le remplir ; ensuite il doit aller déposer avant de pouvoir récolter à nouveau. Rien n'oblige à le remplir avant de déposer : un pion peut revenir au château avec 1 seule unité.
4. Le pion revient **à 1 case de son château** et fait l'action `deposit` : **tout** son chargement passe dans les stocks du camp.
5. Les ressources ne servent qu'une fois **déposées**. Ce que porte un pion n'est pas dépensable.

Points importants :

- On dépose **au château** : c'est le seul bâtiment du jeu.
- Un pion qui porte du bois ne peut pas récolter d'or tant qu'il n'a pas déposé son bois.
- Un pion tué perd son chargement.
- Les stocks n'ont pas de plafond.

---

## 6. Les unités

### 6.1 Caractéristiques

| Unité (`type`) | Nom | PV | Déplacement | Attaque | Soin | Portée | Coût fixe | Recrutée par |
|---|---|---|---|---|---|---|---|---|
| `pawn` | Pion | 30 | 4 | 3 | 0 | 1 | 1 or | `castle` |
| `warrior` | Guerrier | 60 | 3 | 8 | 0 | 1 | 5 or | `castle` |
| `lancer` | Lancier | 90 | 2 | 10 | 0 | 2 | 10 or | `castle` |
| `archer` | Archer | 35 | 1 | 9 | 0 | 4 | 10 or | `castle` |
| `monk` | Moine | 40 | 1 | 0 | 10 | 2 | 15 or | `castle` |

**À ce coût fixe s'ajoute de la viande, qui augmente à chaque recrutement** (voir [§6.2](#62-coût-de-recrutement)).

- **PV** (`hp`) : points de vie. L'unité meurt quand ils tombent à 0 ou moins. Ils ne remontent que grâce aux soins d'un moine, jamais tout seuls.
- **Déplacement** (`move`) : nombre maximum de pas (en 4 directions) par phase de déplacement.
- **Attaque** (`attack`) : dégâts infligés par une action `attack`. `0` = l'unité ne peut pas attaquer.
- **Soin** (`heal`) : PV rendus par une action `heal`. `0` = l'unité ne peut pas soigner.
- **Portée** (`range`) : distance de Chebyshev maximale pour attaquer ou soigner.
- **Coût fixe** (`cost`) : la part en or, payée au moment du recrutement.

### 6.2 Coût de recrutement

Le coût d'un recrutement a deux parties, payées ensemble au moment du recrutement :

1. **Une part fixe en or**, qui dépend du type d'unité : `rules.units[type].cost`, soit 1 or pour un pion, 5 pour un guerrier, 10 pour un lancier ou un archer, 15 pour un moine.
2. **Une part variable en viande**, qui ne dépend **pas** du type d'unité mais du **nombre de recrutements déjà faits par votre camp depuis le début de la partie** :
   - le 1er recrutement coûte **1 viande**, le 2e **2 viandes**, le 3e **3 viandes**, et ainsi de suite ;
   - autrement dit, le n-ième recrutement coûte `n × rules.meat_per_recruit` viandes (`meat_per_recruit` vaut 1) ;
   - les **3 pions de départ ne comptent pas** : votre premier recrutement coûte bien 1 viande ;
   - le compteur **ne redescend jamais**, même si vos unités meurent : il compte les recrutements, pas les unités vivantes ;
   - chaque camp a son propre compteur.

Exemple : si votre camp a déjà recruté 11 unités, recruter un guerrier coûte maintenant **5 or + 12 viandes**. Le recrutement suivant coûtera 13 viandes, quel que soit le type d'unité.

Vous n'avez pas à recalculer ce compteur : l'état l'indique pour chaque camp, dans `teams.<camp>.recruited` (recrutements déjà faits) et `teams.<camp>.next_meat_cost` (viande que coûtera le prochain recrutement). Voir [§14.2](#142-teamscamp).

Coût cumulé en viande : recruter `n` unités au total coûte `1 + 2 + … + n = n × (n + 1) / 2` viandes. Par exemple 10 recrutements coûtent 55 viandes, 20 en coûtent 210, et 37 (le maximum utile avec la limite de 40 unités et 3 pions de départ, si aucune ne meurt) en coûtent 703.

### 6.3 Capacités particulières

| Capacité | Qui |
|---|---|
| Récolter (`gather`), déposer (`deposit`) | **uniquement le pion** |
| Attaquer (`attack`) | toute unité dont `attack > 0` : pion, guerrier, lancier, archer |
| Soigner (`heal`) | toute unité dont `heal > 0` : le moine |

- Le pion est à la fois l'ouvrier et une unité de combat (faible).
- Le moine ne peut pas attaquer. Il peut se soigner lui-même.
- Aucune unité n'a de bonus ou de faiblesse cachée : pas d'armure, pas de dégâts critiques, pas de hasard. **Le jeu est entièrement déterministe.**

### 6.4 Limite d'unités

Un camp ne peut pas avoir plus de **40 unités** vivantes en même temps (`rules.max_units`), pions compris. Le château ne compte pas.

### 6.5 Unités de départ

Chaque camp commence avec **3 pions** placés autour de son château, selon la même règle que les recrues (voir [§10.5](#105-recruit--recruter)). Les pions des deux camps sont donc exactement en miroir l'un de l'autre par rapport au centre de la carte.

---

## 7. Le château

**Le château est le seul bâtiment du jeu.** Chaque camp en a exactement un, posé par la carte au début de la partie. Il est impossible d'en construire d'autres, ni aucun autre bâtiment : il n'existe pas d'action de construction.

| Bâtiment (`type`) | Nom | Taille (l × h) | PV | Recrute |
|---|---|---|---|---|
| `castle` | Château | 4 × 2 | 800 | `pawn`, `warrior`, `lancer`, `archer`, `monk` |

- Le château est décrit par son **coin haut-gauche** (`x`, `y`) et sa taille (`width`, `height`). Il couvre les cases `x` à `x + width - 1` et `y` à `y + height - 1`.
- C'est un **obstacle** : on ne peut ni le traverser ni s'y arrêter.
- C'est là que les pions **déposent** leurs ressources.
- Il **recrute toutes les unités**, mais **une seule par tour** (voir [§10.5](#105-recruit--recruter)). C'est la principale limite de production du jeu : au mieux une unité par tour, quels que soient vos stocks.
- Il peut être attaqué. Il n'attaque pas.
- Il peut être **réparé avec du bois** grâce à l'action `repair` (voir [§10.7](#107-repair--réparer-le-château)), au plus une fois par tour. C'est le seul moyen de lui rendre des PV : il ne se régénère pas tout seul, et les moines ne soignent que les unités.
- **Il est irremplaçable** : sa destruction fait perdre la partie.

---

## 8. Déroulement d'un tour

### 8.1 Séquence

Les tours sont numérotés à partir de 1. Pour chaque tour `N` :

```
1. serveur → IA :  {"type": "new_turn", "turn": N, ...}        (état actuel)
2. IA → serveur :  {"type": "moves",    "turn": N, "moves": [...]}
3. le jeu applique les déplacements des deux camps
4. serveur → IA :  {"type": "action",   "turn": N, ...}        (état après les déplacements)
5. IA → serveur :  {"type": "actions",  "turn": N, "actions": [...]}
6. le jeu applique les actions des deux camps
7. le jeu vérifie la fin de partie ; sinon, tour N+1
```

- Les deux IA reçoivent les messages **en même temps** et répondent **en parallèle**. Vous ne voyez pas les ordres adverses avant de jouer, mais vous voyez leurs effets au message suivant (dans `state` et `events`).
- Le message `game_start` (règles et état initial) précède le premier `new_turn`.

### 8.2 Délai de réponse

- Chaque IA dispose de **5 secondes** par défaut (option `--timeout` du serveur) pour répondre à **chaque** phase. Le délai court à partir de l'envoi du message par le serveur.
- Passé ce délai, le serveur considère que vous n'envoyez **aucun ordre** pour cette phase. Il vous envoie un message `error` et la partie continue normalement.
- Une réponse arrivée en retard est ignorée, avec un message `error`.
- Le délai n'est pas cumulatif : chaque phase repart de zéro.

### 8.3 Numéro de tour

Votre réponse doit reprendre **exactement** le `turn` du message auquel vous répondez. Une réponse avec un autre numéro est ignorée, avec un message `error` ; le serveur continue alors d'attendre la bonne réponse jusqu'à la fin du délai.

### 8.4 Ordres invalides

**Un ordre invalide ne fait jamais planter la partie et n'annule pas les autres ordres.** Il est simplement ignoré. Au message suivant, vous le retrouvez dans la liste `rejected`, accompagné de la raison du refus (voir [§16](#16-liste-complète-des-refus-rejected)). Lisez cette liste pendant le développement : c'est votre meilleur outil de débogage.

---

## 9. Phase de déplacement

### 9.1 Format

```json
{"type": "moves", "turn": 12, "moves": [
  {"unit": 7, "to": [31, 24]},
  {"unit": 9, "to": [30, 22]}
]}
```

| Champ | Type | Description |
|---|---|---|
| `unit` | entier | `id` d'une de **vos** unités. |
| `to` | `[x, y]` | Case d'arrivée. |

Une liste vide (`"moves": []`) est valide : aucune unité ne bouge.

### 9.2 Conditions

Un déplacement est accepté si **toutes** ces conditions sont vraies :

1. l'unité existe et vous appartient ;
2. elle ne s'est pas déjà déplacée pendant cette phase (**un déplacement par unité et par tour**) ;
3. `to` est une case de la carte ;
4. `to` est **marchable** (`ground`, `tree` ou `sheep`) et **libre** (aucune unité dessus, ni alliée ni ennemie) ;
5. il existe un chemin de **`move` pas au plus**, en 4 directions, qui ne passe que par des cases marchables ;
6. ce chemin peut **traverser vos propres unités**, mais **pas les unités ennemies**.

Le jeu calcule lui-même le plus court chemin : vous n'indiquez que la destination.

### 9.3 Cas particuliers

- Un ordre dont `to` est la position actuelle de l'unité est **ignoré sans être refusé**. Il n'apparaît pas dans `rejected` et ne compte pas comme un déplacement.
- Les déplacements sont appliqués **un par un**, dans l'ordre décrit en [§11.1](#111-alternance-entre-les-camps). L'occupation des cases est recalculée après chaque déplacement :
  - une case libérée par une unité qui vient de partir est immédiatement disponible pour les ordres suivants ;
  - si deux unités visent la même case, la première traitée l'obtient et la seconde est refusée ;
  - **dans votre propre liste, l'ordre compte** : si l'unité A doit prendre la place de l'unité B, placez l'ordre de B **avant** celui de A.
- Une unité qui ne reçoit pas d'ordre reste sur place.
- Les unités recrutées pendant la phase d'action précédente peuvent se déplacer dès ce tour-ci.

---

## 10. Phase d'action

### 10.1 Format général

```json
{"type": "actions", "turn": 12, "actions": [
  {"type": "attack",  "unit": 12, "target": 41},
  {"type": "heal",    "unit": 15, "target": 12},
  {"type": "gather",  "unit": 7,  "target": [32, 24]},
  {"type": "deposit", "unit": 8},
  {"type": "recruit", "building": 1, "unit_type": "warrior"},
  {"type": "repair",  "building": 1}
]}
```

Il y a exactement **6 types d'action** : `attack`, `heal`, `gather`, `deposit`, `recruit` et `repair`. Tout autre `type` (y compris `build`) est refusé.

Règles générales :

- **Une seule action par unité et par tour**, quelle qu'elle soit.
- **Un seul recrutement par tour** (le château ne recrute qu'une fois par tour).
- Une liste vide (`"actions": []`) est valide.
- Les champs supplémentaires sont ignorés.
- Les `id` (`unit`, `target`, `building`) doivent être des **nombres JSON**. Une chaîne comme `"12"` n'est pas reconnue.

### 10.2 `attack` — attaquer

```json
{"type": "attack", "unit": 12, "target": 41}
```

| Champ | Description |
|---|---|
| `unit` | Votre unité qui attaque. |
| `target` | `id` d'une **unité ennemie ou du château ennemi**. |

Conditions : l'unité vous appartient, n'a pas déjà agi, a une `attack` supérieure à 0, et la cible existe, appartient à l'adversaire et se trouve **à `range` cases ou moins** (Chebyshev, case la plus proche pour le château).

Effet : la cible perd `attack` PV. Les dégâts sont **simultanés** (voir [§11.2](#112-ordre-de-résolution-de-la-phase-daction)).

### 10.3 `heal` — soigner

```json
{"type": "heal", "unit": 15, "target": 12}
```

Conditions : l'unité vous appartient, n'a pas déjà agi, a un `heal` supérieur à 0 (moine), et la cible est **une de vos unités** (pas le château) **à `range` cases ou moins**. Un moine peut se soigner lui-même.

Effet : la cible regagne `heal` PV, sans dépasser son maximum (`max_hp`). Soigner une unité déjà en pleine santé est accepté, mais ne sert à rien et consomme l'action.

### 10.4 `gather` — récolter

```json
{"type": "gather", "unit": 7, "target": [32, 24]}
```

| Champ | Description |
|---|---|
| `unit` | Un de vos **pions**. |
| `target` | Position `[x, y]` d'un gisement (`gold`, `tree` ou `sheep`). |

Conditions :
- l'unité est un pion qui vous appartient et n'a pas déjà agi ;
- il y a bien un gisement en `target` ;
- le pion est **à 1 case** du gisement (Chebyshev : diagonales comprises, ou sur la case du gisement s'il est marchable) ;
- s'il porte déjà quelque chose, c'est **la même ressource** ;
- il n'est pas plein.

Effet : le pion prélève 1 unité (`gather_amount`), à condition de ne pas dépasser `carry_capacity` (5). Le gisement est inépuisable : il ne diminue pas et ne disparaît jamais.

### 10.5 `recruit` — recruter

```json
{"type": "recruit", "building": 1, "unit_type": "warrior"}
```

| Champ | Description |
|---|---|
| `building` | `id` de **votre château** (lisible dans `state.buildings`). |
| `unit_type` | `"pawn"`, `"warrior"`, `"lancer"`, `"archer"` ou `"monk"`. |

Conditions (vérifiées dans cet ordre) :
1. le bâtiment existe et vous appartient (c'est forcément votre château) ;
2. il n'a pas déjà recruté pendant ce tour : **un seul recrutement par tour**, les ordres `recruit` suivants sont refusés ;
3. `unit_type` fait partie de sa liste `recruits` (les 5 types d'unités) ;
4. vous avez moins de 40 unités ;
5. il existe une **case marchable et libre autour** du château (à distance 1 de son emprise) ;
6. vous avez les ressources nécessaires : l'or fixe de l'unité **et** la viande du prochain recrutement (`next_meat_cost`, voir [§6.2](#62-coût-de-recrutement)).

Effet : le coût est payé, le compteur de recrutements de votre camp augmente de 1 (le recrutement suivant coûtera donc une viande de plus), et l'unité apparaît, avec tous ses PV, sur la **première case libre** trouvée autour du château (cases marchables à distance 1 de son emprise). L'ordre de parcours dépend du camp, pour respecter la symétrie de la carte :
- **purple** parcourt l'anneau ligne par ligne, de haut en bas et de gauche à droite, en partant du **coin haut-gauche** ;
- **yellow** le parcourt exactement à l'envers, de bas en haut et de droite à gauche, en partant du **coin bas-droit**.

Les deux camps placent ainsi leurs unités en miroir l'un de l'autre. Elle reçoit un nouvel `id`. Elle ne peut pas agir pendant la phase où elle est créée (vous ne connaissez pas encore son `id`), mais elle peut se déplacer et agir dès le tour suivant.

### 10.6 `deposit` — déposer

```json
{"type": "deposit", "unit": 8}
```

Conditions : l'unité est un pion qui vous appartient, n'a pas déjà agi, porte quelque chose, et se trouve **à 1 case de votre château** (Chebyshev, case la plus proche du château).

Effet : tout le chargement est ajouté aux stocks du camp, et le pion repart les mains vides.

### 10.7 `repair` — réparer le château

```json
{"type": "repair", "building": 1}
```

| Champ | Description |
|---|---|
| `building` | `id` de **votre château**. |

C'est un ordre donné **au château**, pas à une unité : aucune unité n'a besoin d'être à côté, et aucune unité ne consomme son action.

Conditions (vérifiées dans cet ordre) :
1. le bâtiment existe et vous appartient (c'est forcément votre château) ;
2. il n'a pas déjà été réparé pendant ce tour : **une seule réparation par tour** ;
3. vous avez **au moins 1 bois** en stock.

Effet :
- **tout le bois de votre stock est consommé**, quelle que soit la quantité ;
- le château regagne autant de PV que de bois consommé (`rules.repair_hp_per_wood` PV par bois, soit 1), **sans dépasser ses PV maximum** (800) ;
- **le surplus est perdu** : le bois qui dépasse les PV manquants est consommé quand même, sans effet.

Exemples, pour un château à 750 PV sur 800 (il manque 50 PV) :

| Bois en stock | PV regagnés | Château après | Bois après | Bois gaspillé |
|---|---|---|---|---|
| 30 | 30 | 780 | 0 | 0 |
| 50 | 50 | 800 | 0 | 0 |
| 80 | 50 | 800 | 0 | **30** |

Points importants :
- Réparer un château **déjà à 800 PV** est accepté : **tout le bois est perdu** et rien n'est réparé.
- La réparation est **indépendante du recrutement** : le château peut recruter une unité **et** être réparé pendant le même tour.
- La réparation se fait à l'étape 3 de la phase d'action, donc **après les dégâts** du tour (voir [§11.2](#112-ordre-de-résolution-de-la-phase-daction)). Elle ne peut pas empêcher la destruction d'un château qui tombe à 0 PV pendant ce tour.
- Le bois déposé pendant la même étape compte, s'il est traité avant : placez vos `deposit` **avant** le `repair` dans votre liste.
- Pour ne rien gaspiller, réparez quand votre stock de bois est **inférieur ou égal** aux PV manquants (`max_hp - hp` du château).

---

## 11. Ordre de résolution et cas limites

### 11.1 Alternance entre les camps

Dans chaque phase, les ordres des deux camps sont traités **en alternance** :

```
ordre n°1 du camp A, ordre n°1 du camp B, ordre n°2 du camp A, ordre n°2 du camp B, ...
```

- Aux tours **impairs** (1, 3, 5…), le camp A est **purple**. Aux tours **pairs**, c'est **yellow**.
- Quand un camp a épuisé sa liste, les ordres restants de l'autre camp sont traités à la suite.
- **L'ordre de votre liste détermine donc l'ordre de traitement de vos ordres.** Mettez en premier ceux qui comptent le plus, par exemple quand une case ou une ressource est disputée, ou quand les stocks ne suffisent pas pour tout.

### 11.2 Ordre de résolution de la phase d'action

La phase d'action se déroule en trois étapes :

**Étape 1 — Planification du combat.** Tous les ordres sont parcourus en alternance. Les `attack` et `heal` sont vérifiés et **enregistrés**, mais pas encore appliqués. Les autres ordres sont mis de côté. Une attaque ou un soin accepté consomme l'action de l'unité **dès cette étape**.

**Étape 2 — Résolution simultanée du combat.**
1. Tous les **soins** sont appliqués (plafonnés au maximum de PV).
2. Puis tous les **dégâts** sont appliqués. Les dégâts de plusieurs attaquants sur une même cible s'additionnent.
3. Les unités à 0 PV ou moins meurent, et un château à 0 PV ou moins est détruit.

Conséquences :
- **Une unité tuée pendant ce tour frappe quand même** : toutes les attaques ont été enregistrées sur l'état de début de phase. Deux unités peuvent donc s'entretuer.
- Un soin peut sauver une unité, car il est appliqué avant les dégâts. Par exemple, une unité à 5 PV soignée de 10 puis frappée de 12 survit avec 3 PV.
- Attaquer une unité déjà condamnée par les autres attaques de ce tour gaspille des dégâts : c'est le principe du « tir concentré » à doser.

**Étape 3 — Économie et production.** Les ordres `gather`, `deposit`, `recruit` et `repair` mis de côté sont traités **un par un**, toujours en alternance :
- une unité morte à l'étape 2 ne peut plus agir : son ordre est refusé avec « introuvable » ;
- une unité qui a déjà attaqué ou soigné à l'étape 1 ne peut pas aussi récolter : son ordre est refusé, **même s'il était placé avant dans votre liste** ;
- les ressources sont dépensées au fur et à mesure : si vous demandez plus que vos stocks, les premiers ordres traités passent et les suivants sont refusés ;
- un dépôt fait pendant cette étape peut financer un recrutement ou une réparation traités **plus loin dans la même étape** (pour vos propres ordres, mettez donc les `deposit` en premier) ;
- une réparation ne sauve pas un château détruit à l'étape 2 : il n'existe plus, l'ordre est refusé.

**Enfin**, la fin de partie est vérifiée.

### 11.3 Cas limites divers

- Le château peut être détruit à l'étape 2 : un `deposit` traité ensuite échoue, car il n'y a plus de château.
- Plusieurs pions peuvent récolter le même gisement le même tour, sans limite.
- Une unité peut se déplacer puis agir pendant le même tour (c'est même le cas normal).
- Les gisements et les châteaux ne bougent jamais.
- Les `id` ne sont **jamais réutilisés**, même après la mort d'une unité.

---

## 12. Fin de partie

La fin de partie est vérifiée **à la fin de chaque phase d'action**.

| Situation | Vainqueur (`winner`) | Raison (`reason`) |
|---|---|---|
| Le château yellow est détruit, le purple tient. | `"purple"` | `castle_destroyed` |
| Le château purple est détruit, le yellow tient. | `"yellow"` | `castle_destroyed` |
| Les deux châteaux sont détruits le même tour. | `"draw"` | `castle_destroyed` |
| Le tour `max_turns` est terminé sans château détruit. | Le camp dont le château a **le plus de PV**, `"draw"` en cas d'égalité. | `max_turns` |
| Une IA se déconnecte pendant la partie. | L'autre camp. | `opponent_disconnected` |
| Le jeu Godot est fermé, ou on revient au menu avec Échap. | `null` (aucun) | `engine_disconnected` |

- Avec `max_turns = 500`, les 500 tours sont joués intégralement. Le classement est fait après la phase d'action du tour 500.
- Se déconnecter fait perdre la partie : faites en sorte que votre IA ne plante pas (voir [§21](#21-pièges-fréquents-et-faq)).
- Une déconnexion **avant** le début de la partie libère simplement la place.

---

## 13. Référence des messages

Notation : `→` = message envoyé par votre IA au serveur ; `←` = message reçu du serveur.

### 13.1 Messages que vous envoyez

#### `join` — rejoindre une partie

```json
→ {"type": "join", "game_id": "K3P9QZ", "name": "mon-ia", "team": "purple"}
```

| Champ | Obligatoire | Description |
|---|---|---|
| `game_id` | oui | ID de la partie (6 caractères). Majuscules et minuscules sont acceptées, et les espaces autour sont ignorés. |
| `name` | non | Nom affiché dans le jeu (32 caractères max). Par défaut : `"anonyme"`. |
| `team` | non | `"purple"` ou `"yellow"` : camp souhaité, accordé s'il est libre. Sinon, ou si le champ est absent, vous recevez la première place libre (purple d'abord). |

#### `moves` — vos déplacements

```json
→ {"type": "moves", "turn": 12, "moves": [{"unit": 7, "to": [31, 24]}]}
```

À envoyer en réponse à `new_turn`. Voir [§9](#9-phase-de-déplacement).

#### `actions` — vos actions

```json
→ {"type": "actions", "turn": 12, "actions": [{"type": "deposit", "unit": 8}]}
```

À envoyer en réponse à `action`. Voir [§10](#10-phase-daction).

### 13.2 Messages que vous recevez

#### `joined` — confirmation

```json
← {"type": "joined", "game_id": "K3P9QZ", "team": "purple", "name": "mon-ia"}
```

`team` est **votre camp** pour toute la partie.

#### `game_start` — début de partie (reçu une seule fois)

```json
← {"type": "game_start", "game_id": "K3P9QZ", "you": "purple", "opponent": "Robot",
   "rules": { ... }, "state": { ... }}
```

| Champ | Description |
|---|---|
| `you` | Votre camp. |
| `opponent` | Nom de l'adversaire. |
| `rules` | Toutes les constantes du jeu (voir ci-dessous). |
| `state` | L'état initial (tour 0). |

Contenu de `rules` :

```json
{
  "legend": ["water", "ground", "rock", "gold", "tree", "sheep",
             "castle_purple", "castle_yellow"],
  "walkable": ["ground", "tree", "sheep"],
  "distance": "chebyshev",
  "max_turns": 500,
  "start_resources": {"gold": 0, "wood": 0, "meat": 0},
  "max_units": 40,
  "meat_per_recruit": 1,
  "repair_hp_per_wood": 1,
  "carry_capacity": 5,
  "gather_amount": 1,
  "units": {
    "pawn":    {"hp": 30, "move": 4, "attack": 3,  "heal": 0,  "range": 1, "cost": {"gold": 1}},
    "warrior": {"hp": 60, "move": 3, "attack": 8,  "heal": 0,  "range": 1, "cost": {"gold": 5}},
    "lancer":  {"hp": 90, "move": 2, "attack": 10, "heal": 0,  "range": 2, "cost": {"gold": 10}},
    "archer":  {"hp": 35, "move": 1, "attack": 9,  "heal": 0,  "range": 4, "cost": {"gold": 10}},
    "monk":    {"hp": 40, "move": 1, "attack": 0,  "heal": 10, "range": 2, "cost": {"gold": 15}}
  },
  "buildings": {
    "castle": {"width": 4, "height": 2, "hp": 800,
               "recruits": ["pawn", "warrior", "lancer", "archer", "monk"]}
  }
}
```

(L'ordre des clés à l'intérieur d'un objet JSON n'est pas garanti : accédez aux champs par leur nom.)

#### `new_turn` — début d'un tour, phase de déplacement

```json
← {"type": "new_turn", "turn": 12, "you": "purple", "state": {...},
   "events": [...], "rejected": [...]}
```

| Champ | Description |
|---|---|
| `turn` | Numéro du tour en cours. **C'est lui qu'il faut renvoyer.** |
| `you` | Votre camp. |
| `state` | L'état actuel, c'est-à-dire après la phase d'action du tour précédent. |
| `events` | Ce qui s'est passé pendant la phase d'action du tour précédent (vide au tour 1). |
| `rejected` | **Vos** actions refusées au tour précédent (vide au tour 1). |

Réponse attendue : `moves`.

#### `action` — phase d'action

```json
← {"type": "action", "turn": 12, "you": "purple", "state": {...},
   "events": [...], "rejected": [...]}
```

| Champ | Description |
|---|---|
| `turn` | Numéro du tour en cours (le même que le `new_turn` correspondant). |
| `state` | L'état après les déplacements de ce tour. |
| `events` | Les déplacements de ce tour, des deux camps. |
| `rejected` | **Vos** déplacements refusés à ce tour. |

Réponse attendue : `actions`.

#### `game_over` — fin de partie

```json
← {"type": "game_over", "winner": "yellow", "reason": "castle_destroyed",
   "state": {...}, "events": [...], "rejected": [...]}
```

| Champ | Description |
|---|---|
| `winner` | `"purple"`, `"yellow"`, `"draw"` ou `null`. |
| `reason` | Voir [§12](#12-fin-de-partie). |
| `state` | L'état final, ou `null` en cas de déconnexion. |
| `events`, `rejected` | Ceux de la dernière phase d'action (vides en cas de déconnexion). |

Le serveur ferme la connexion juste après ce message.

#### `error` — information du serveur

```json
← {"type": "error", "message": "delai depasse pour 'moves' au tour 3 : aucun ordre retenu"}
```

Ce message est **purement informatif** : la partie continue. Il peut arriver à tout moment, entre deux autres messages, et votre boucle de lecture doit savoir l'ignorer ou l'afficher. Il n'y a qu'une exception : une erreur reçue **avant** `joined` signifie que vous n'avez pas pu rejoindre la partie. Liste complète en [§17](#17-liste-complète-des-erreurs-serveur).

### 13.3 Messages réservés au jeu Godot

Pour information, ces messages circulent entre le serveur et le jeu. Vous n'avez **pas** à les envoyer ni à les traiter : `create_game`, `game_created`, `ready`, `player_joined`, `player_left`, `moves` (version serveur → jeu, avec les ordres des deux camps), `done`, `actions` (version serveur → jeu), `action_done`.

### 13.4 Exemple d'échange complet

```
→ {"type":"join","game_id":"K3P9QZ","name":"mon-ia"}
← {"type":"joined","game_id":"K3P9QZ","team":"purple","name":"mon-ia"}
   ... attente de l'adversaire ...
← {"type":"game_start","game_id":"K3P9QZ","you":"purple","opponent":"Robot","rules":{...},"state":{...}}
← {"type":"new_turn","turn":1,"you":"purple","state":{...},"events":[],"rejected":[]}
→ {"type":"moves","turn":1,"moves":[{"unit":3,"to":[24,22]}]}
← {"type":"action","turn":1,"you":"purple","state":{...},"events":[{"type":"move","unit":3,"from":[25,24],"to":[24,22]}, ...],"rejected":[]}
→ {"type":"actions","turn":1,"actions":[{"type":"recruit","building":1,"unit_type":"pawn"}]}
← {"type":"new_turn","turn":2,"you":"purple","state":{...},"events":[{"type":"recruit",...}],"rejected":[]}
   ...
← {"type":"game_over","winner":"purple","reason":"castle_destroyed","state":{...},"events":[...],"rejected":[]}
```

---

## 14. Référence de l'état (`state`)

```json
{
  "turn": 12,
  "phase": "move",
  "width": 80,
  "height": 71,
  "grid": [[0, 0, 0, ...], [0, 1, 1, ...], ...],
  "teams": {
    "purple": {"name": "mon-ia", "resources": {"gold": 20, "wood": 35, "meat": 60}, "unit_count": 7,
               "recruited": 4, "next_meat_cost": 5},
    "yellow": {"name": "Robot",  "resources": {"gold": 0,  "wood": 80, "meat": 15}, "unit_count": 6,
               "recruited": 3, "next_meat_cost": 4}
  },
  "units": [
    {"id": 3, "team": "purple", "type": "pawn", "x": 24, "y": 22, "hp": 30, "max_hp": 30,
     "carrying": {"resource": "wood", "amount": 5}},
    {"id": 6, "team": "yellow", "type": "warrior", "x": 50, "y": 46, "hp": 64, "max_hp": 80,
     "carrying": null}
  ],
  "buildings": [
    {"id": 1, "team": "purple", "type": "castle", "x": 25, "y": 25, "width": 4, "height": 2,
     "hp": 800, "max_hp": 800}
  ],
  "resources": [
    {"x": 32, "y": 24, "resource": "wood"}
  ],
  "winner": null,
  "end_reason": null
}
```

### 14.1 Champs de premier niveau

| Champ | Type | Description |
|---|---|---|
| `turn` | entier | Numéro du **dernier tour dont une phase a été appliquée**. Attention : dans `new_turn`, il vaut le numéro du tour **précédent** (et 0 au tour 1). Dans `action`, il vaut le tour en cours. **Pour répondre, utilisez toujours le `turn` du message, pas celui de `state`.** |
| `phase` | texte | Dernière phase appliquée : `"waiting"` (avant le tour 1), `"move"`, `"action"` ou `"over"`. |
| `width`, `height` | entiers | Dimensions de la carte. |
| `grid` | liste de listes d'entiers | `grid[y][x]` = code de terrain (voir [§4.2](#42-codes-de-terrain)). |
| `teams` | objet | Une entrée par camp (`purple`, `yellow`). |
| `units` | liste | Toutes les unités vivantes **des deux camps**, triées par `id`. |
| `buildings` | liste | Les châteaux encore debout **des deux camps**, triés par `id` (donc 2 entrées pendant toute la partie). |
| `resources` | liste | Tous les gisements de la carte. La liste ne change jamais pendant la partie. |
| `winner` | texte ou `null` | Vainqueur si la partie est finie : `"purple"`, `"yellow"` ou `"draw"`. |
| `end_reason` | texte ou `null` | Raison de la fin (voir [§12](#12-fin-de-partie)). |

### 14.2 `teams.<camp>`

| Champ | Description |
|---|---|
| `name` | Nom de l'IA qui joue ce camp. |
| `resources` | Stocks **déposés** : `{"gold": …, "wood": …, "meat": …}`. |
| `unit_count` | Nombre d'unités vivantes du camp. |
| `recruited` | Nombre de recrutements déjà faits par le camp depuis le début (les pions de départ ne comptent pas). Ne diminue jamais. |
| `next_meat_cost` | Viande que coûtera le **prochain** recrutement du camp, quel que soit le type d'unité : `(recruited + 1) × meat_per_recruit`. |

### 14.3 Une unité (`units[i]`)

| Champ | Description |
|---|---|
| `id` | Identifiant unique, jamais réutilisé. |
| `team` | `"purple"` ou `"yellow"`. |
| `type` | `"pawn"`, `"warrior"`, `"lancer"`, `"archer"` ou `"monk"`. |
| `x`, `y` | Position. |
| `hp`, `max_hp` | PV actuels et maximum. |
| `carrying` | `null` si l'unité ne porte rien, sinon `{"resource": "gold"\|"wood"\|"meat", "amount": n}`. Ne concerne que les pions. |

### 14.4 Un château (`buildings[i]`)

| Champ | Description |
|---|---|
| `id` | Identifiant unique. Il partage la même numérotation que les unités : un `id` ne désigne jamais à la fois une unité et un château. |
| `team` | Camp propriétaire. |
| `type` | Toujours `"castle"`. |
| `x`, `y` | Coin **haut-gauche**. |
| `width`, `height` | Taille de l'emprise. |
| `hp`, `max_hp` | PV actuels et maximum. |

### 14.5 Un gisement (`resources[i]`)

| Champ | Description |
|---|---|
| `x`, `y` | Position. |
| `resource` | `"gold"`, `"wood"` ou `"meat"`. |

Les gisements n'ont pas d'`id` : on les désigne par leur position. Ils n'ont pas de quantité : ils sont inépuisables.

### 14.6 Numérotation initiale (pour information)

Au début de la partie, les `id` sont attribués dans cet ordre : château purple = **1**, château yellow = **2**, puis les 3 pions purple (**3, 4, 5**), puis les 3 pions yellow (**6, 7, 8**). Les objets créés ensuite reçoivent 9, 10, 11… dans l'ordre de leur création, tous camps confondus. **Ne codez pas ces numéros en dur** : relisez-les dans l'état.

---

## 15. Référence des événements (`events`)

Les événements décrivent ce qui s'est passé pendant la **phase précédente**, pour **les deux camps**. Ils permettent de comprendre ce qu'a fait l'adversaire. Ils sont donnés dans l'ordre où ils se sont produits.

| `type` | Champs | Signification |
|---|---|---|
| `move` | `unit`, `from: [x,y]`, `to: [x,y]` | Une unité s'est déplacée. |
| `attack` | `unit`, `target`, `amount` | `unit` a infligé `amount` dégâts à `target` (unité ou château). |
| `heal` | `unit`, `target`, `amount` | `unit` a soigné `target` de `amount` PV (avant plafonnement). |
| `unit_killed` | `unit`, `team` | Une unité est morte. |
| `building_destroyed` | `building`, `team`, `building_type` | Un château a été détruit (`building_type` vaut toujours `"castle"`) : la partie se termine. |
| `gather` | `unit`, `resource`, `amount`, `at: [x,y]` | Un pion a récolté. |
| `deposit` | `unit`, `resource`, `amount` | Un pion a déposé au château. |
| `recruit` | `building`, `unit`, `unit_type`, `at: [x,y]` | Une unité a été recrutée. `unit` est son nouvel `id`. |
| `repair` | `building`, `wood`, `amount` | Un château a été réparé : `wood` bois consommés, `amount` PV réellement regagnés (inférieur à `wood` si du bois a été gaspillé). |

Exemples :

```json
{"type": "move", "unit": 3, "from": [25, 24], "to": [24, 22]}
{"type": "attack", "unit": 12, "target": 41, "amount": 12}
{"type": "heal", "unit": 15, "target": 12, "amount": 10}
{"type": "unit_killed", "unit": 41, "team": "yellow"}
{"type": "building_destroyed", "building": 2, "team": "yellow", "building_type": "castle"}
{"type": "gather", "unit": 7, "resource": "wood", "amount": 1, "at": [32, 24]}
{"type": "deposit", "unit": 8, "resource": "gold", "amount": 10}
{"type": "recruit", "building": 1, "unit": 45, "unit_type": "pawn", "at": [24, 24]}
{"type": "repair", "building": 1, "wood": 80, "amount": 50}
```

---

## 16. Liste complète des refus (`rejected`)

Chaque refus a la forme `{"order": <votre ordre tel que vous l'avez envoyé>, "reason": "<texte>"}`. Les messages sont en français, sans accents. Dans le tableau, `X` désigne une valeur variable.

### 16.1 Déplacements

| Raison | Cause |
|---|---|
| `un ordre doit etre un objet JSON` | L'élément de la liste n'est pas un objet `{...}`. |
| `unite X introuvable dans votre camp` | `unit` absent, mal typé, inexistant, mort ou appartenant à l'adversaire. |
| `cette unite s'est deja deplacee ce tour` | Deuxième ordre de déplacement pour la même unité. |
| `'to' doit etre [x, y] dans la carte` | `to` absent, mal formé, négatif ou hors de la carte. |
| `destination occupee, infranchissable ou hors de portee` | Case non marchable, déjà occupée, ou impossible à atteindre en `move` pas (obstacles, unités ennemies sur le chemin). |

### 16.2 Actions

| Raison | Action | Cause |
|---|---|---|
| `un ordre doit etre un objet JSON` | toutes | L'élément n'est pas un objet. |
| `type inconnu (attack, heal, gather, deposit, recruit, repair)` | toutes | `type` absent ou non reconnu (par exemple `build`, qui n'existe pas). |
| `unite X introuvable dans votre camp` | attack, heal, gather, deposit | Unité inexistante, morte (y compris pendant ce tour) ou ennemie. |
| `X a deja agi ce tour` | toutes | L'unité `X` a déjà une action acceptée ce tour, ou le château `X` a déjà recruté ce tour. |
| `un X ne peut pas faire 'attack'` | attack | Unité sans attaque (moine). |
| `un X ne peut pas faire 'heal'` | heal | Unité sans soin. |
| `cible X introuvable` | attack, heal | Aucune unité ni aucun château avec cet `id`. |
| `on n'attaque pas son propre camp` | attack | Cible alliée. |
| `on ne soigne que ses propres unites` | heal | Cible ennemie, ou cible qui est un château. |
| `cible hors de portee (R)` | attack, heal | Cible à plus de `R` cases. |
| `seuls les pions (pawn) peuvent faire 'X'` | gather, deposit | L'unité n'est pas un pion. |
| `pas de ressource en 'target'` | gather | Pas de gisement à cette position, ou `target` mal formé. |
| `ressource trop loin (il faut etre a 1 case)` | gather | Gisement à plus d'une case. |
| `le pion porte deja une autre ressource : deposez-la d'abord` | gather | Type de ressource différent de celui porté. |
| `le pion est deja plein` | gather | Le pion porte déjà 5 unités (`carry_capacity`) : il doit déposer. |
| `le pion ne porte rien` | deposit | Rien à déposer. |
| `il faut etre a 1 case de son chateau pour deposer` | deposit | Trop loin du château, ou château détruit. |
| `ressources insuffisantes (cout : {...})` | recruit | Stocks insuffisants **au moment où l'ordre est traité**. Le coût affiché comprend l'or fixe et la viande du recrutement (par exemple `{"gold":5,"meat":12}`). |
| `batiment X introuvable dans votre camp` | recruit | `building` n'est pas l'`id` de votre château. |
| `un castle recrute seulement pawn, warrior, lancer, archer, monk` | recruit | `unit_type` absent ou inconnu. |
| `limite de 40 unites atteinte` | recruit | Vous avez déjà 40 unités. |
| `aucune case libre autour du batiment` | recruit | Toutes les cases autour du château sont occupées ou non marchables. |
| `batiment X introuvable dans votre camp` | repair | `building` n'est pas l'`id` de votre château (ou il vient d'être détruit). |
| `le chateau a deja ete repare ce tour` | repair | Deuxième ordre `repair` dans le même tour. |
| `aucun bois en stock` | repair | Votre stock de bois est à 0 au moment où l'ordre est traité. |

---

## 17. Liste complète des erreurs serveur

Messages `{"type": "error", "message": "..."}` que le serveur peut vous envoyer :

| Message | Cause | Conséquence |
|---|---|---|
| `chaque ligne doit etre un objet JSON` | Ligne illisible. | Ligne ignorée. |
| `commencez par 'create_game' ou 'join'` | Premier message autre que `join`. | Message ignoré, vous pouvez réessayer. |
| `aucune partie 'X'` | ID inconnu ou partie terminée. | Vous n'êtes pas dans une partie. |
| `la partie X est complete` | Deux joueurs déjà présents, ou partie commencée. | Vous n'êtes pas dans une partie. |
| `message 'X' inattendu, le serveur attend 'Y'` | Mauvais type de réponse (par exemple `moves` pendant la phase d'action). | Message ignoré. |
| `'X' du tour N ignore, tour en cours : M` | Mauvais numéro de tour. | Message ignoré ; le serveur attend toujours votre réponse. |
| `'moves' doit etre une liste` / `'actions' doit etre une liste` | Le champ n'est pas une liste. | Aucun ordre retenu pour cette phase. |
| `delai depasse pour 'X' au tour N : aucun ordre retenu` | Réponse trop tardive. | Aucun ordre retenu pour cette phase. |

---

## 18. Chiffres utiles

Ces tableaux découlent directement des valeurs actuelles des règles. Ils sont fournis pour gagner du temps ; recalculez-les si `rules` change.

### 18.1 Nombre de coups pour détruire une cible

Le tableau donne le nombre d'attaques nécessaires (arrondi au supérieur), sans soin.

| Attaquant (dégâts) → / Cible ↓ | Pion (3) | Guerrier (8) | Lancier (10) | Archer (9) |
|---|---|---|---|---|
| Pion (30 PV) | 10 | 4 | 3 | 4 |
| Guerrier (60 PV) | 20 | 8 | 6 | 7 |
| Lancier (90 PV) | 30 | 12 | 9 | 10 |
| Archer (35 PV) | 12 | 5 | 4 | 4 |
| Moine (40 PV) | 14 | 5 | 4 | 5 |
| **Château (800 PV)** | 267 | **100** | 80 | 89 |

Exemples :
- 6 guerriers abattent un château en 17 tours (6 × 8 = 48 dégâts par tour).
- En duel, un lancier tue un guerrier en 6 coups, et il lui en faut 12 pour mourir : le guerrier est l'unité de base, rapide et bon marché, mais il perd face aux unités à 10 or.
- Un archer au contact d'un guerrier meurt en 5 coups et en donne 7, mais avec sa portée de 4 il tire en général 1 ou 2 fois avant que le guerrier n'arrive.
- Un moine (10 PV par tour) compense entièrement un archer (9 dégâts par tour).

### 18.2 Économie

- Un pion récolte **1 unité par tour** au mieux. C'est le plafond absolu de revenu d'un pion.
- Remplir un pion : **5 récoltes**, donc 5 tours sur place. Un aller-retour complet prend ces tours de récolte, plus le trajet aller, le trajet retour et 1 tour de dépôt.
- Les gisements étant inépuisables, le revenu d'un pion ne dépend que de ce temps de trajet. Un pion qui rapporte `c` unités par voyage en `T` tours gagne `c / T` unités par tour. Exemple : un gisement à 4 pas du château, pour un pion qui marche 4 cases par tour : 1 tour d'aller (avec la première récolte dans le même tour), 4 autres tours de récolte, 1 tour de retour (avec le dépôt dans le même tour), soit 5 unités en 6 tours, environ **0,8 unité par tour**. Pour un gisement à 12 pas (3 tours de trajet), il faut 3 tours d'aller, 5 tours de récolte en tout (dont celui de l'arrivée) et 3 tours de retour (dont celui du dépôt), soit 5 unités en 10 tours, **0,5 unité par tour** : la distance pèse lourd.
- Plus le gisement est loin, plus il vaut la peine de remplir complètement le pion avant de revenir. Pour un gisement collé au château, déposer plus souvent ne coûte presque rien.
- Le revenu d'un camp est donc d'environ **0,5 à 0,8 unité par pion et par tour** selon la distance des gisements : 8 pions rapportent de 4 à 6 unités par tour.
- Comme le pion peut se déplacer puis agir pendant le même tour, l'arrivée et la première récolte, ou le retour et le dépôt, peuvent se faire dans le même tour.
- Le revenu total d'un camp est donc proportionnel à son nombre de pions et à la proximité des gisements qu'il exploite.
- **Au début, c'est l'or qui limite** : vous commencez sans or, et chaque unité en demande. Les premiers pions doivent aller à la mine d'or.
- **Plus la partie avance, plus la viande pèse** : le 20e recrutement coûte à lui seul 20 viandes. Il faut donc déplacer progressivement des pions vers les moutons.
- **Le bois ne sert qu'à réparer le château** (1 bois = 1 PV). Inutile tant que votre château est intact ; précieux quand il est attaqué. Un pion qui récolte du bois rend au mieux environ 1 PV de château par tour, alors qu'un guerrier ennemi lui en retire 8.

### 18.3 Coût de recrutement

Coût en viande selon le rang du recrutement (avec `meat_per_recruit = 1`) :

| Recrutements | Viande du dernier | Viande cumulée |
|---|---|---|
| 1er | 1 | 1 |
| 5e | 5 | 15 |
| 10e | 10 | 55 |
| 15e | 15 | 120 |
| 20e | 20 | 210 |
| 30e | 30 | 465 |
| 37e | 37 | 703 |

Coût en or de quelques compositions (à ajouter à la viande ci-dessus selon le nombre total de recrutements) :

| Composition | Or |
|---|---|
| 5 pions | 5 |
| 6 guerriers | 30 |
| 4 lanciers | 40 |
| 4 archers | 40 |
| 2 moines | 30 |

Exemple : 5 pions puis 6 guerriers, soit 11 recrutements, coûtent 5 + 30 = 35 or et 1 + 2 + … + 11 = 66 viandes.

Le château ne recrutant qu'une unité par tour, une armée de 10 unités demande au moins 10 tours de production, même avec des stocks pleins.

### 18.4 Vitesse

Une unité qui se déplace de `move` cases par tour met au moins `pas / move` tours pour faire un trajet. Il faut entre 14 et 45 pas (médiane 30) pour aller d'une base à l'autre, ce qui donne :

| Unité | `move` | Trajet base à base (min – médiane – max) |
|---|---|---|
| Pion | 4 | 4 – 8 – 12 tours |
| Guerrier | 3 | 5 – 10 – 15 tours |
| Lancier | 2 | 7 – 15 – 23 tours |
| Archer, moine | 1 | 14 – 30 – 45 tours |

---

## 19. Le robot adversaire

En mode « Jouer contre un robot », le serveur lance automatiquement le programme `clients/robot_bot.py`, qui joue **yellow**. Son code source est fourni : vous pouvez le lire, vous en inspirer, ou le lancer vous-même contre votre IA (`py clients/robot_bot.py K3P9QZ --team yellow`).

Sa stratégie :

- **Économie** : il monte jusqu'à 8 pions, répartis entre l'or et la viande selon ses besoins : il vise 40 or en stock et de quoi payer la viande de ses 5 prochains recrutements. Il ne récolte du bois que si son château a perdu au moins 30 PV.
- **Réparation** : il répare quand son bois couvre tous les dégâts (pour ne rien gaspiller), ou tout de suite si son château est sous la moitié de ses PV.
- **Production** (une unité par tour, au château) : ses 4 premiers pions passent avant tout. Ensuite, tant qu'il a moins de 8 pions, il alterne pions et armée. Son armée compte deux guerriers pour un lancier, et au plus 3 archers (un archer pour trois guerriers ou lanciers). S'il est attaqué, il ne recrute plus que des combattants. Quand l'unité voulue n'est pas abordable, il prend la suivante dans son ordre de préférence.
- **Armée** : ses guerriers et lanciers se regroupent autour du château, puis partent à l'assaut du château ennemi **dès qu'ils sont 6**. L'assaut s'arrête quand il ne lui reste plus qu'une seule de ces unités. Les archers restent en défense.
- **Combat** : ses unités poursuivent tout ennemi à moins de 5 cases. Il concentre ses tirs pour achever les cibles, en visant d'abord les archers et les moines, puis les guerriers et les lanciers, puis les pions, et enfin le château.
- **Défense** : si un ennemi s'approche à moins de 10 cases de son château, toutes ses unités situées à moins de 15 cases reviennent défendre.

Il ne recrute pas de moine.

---

## 20. Fichiers fournis

| Fichier | Contenu |
|---|---|
| `clients/template_bot.py` | **Point de départ** : la connexion au serveur, prête à l'emploi. À vous d'écrire le traitement des messages et vos ordres. |
| `clients/rts_client.py` | Petite bibliothèque facultative : connexion, accès à l'état (vos unités, celles de l'adversaire, votre château…), distances, recherche de chemin. |
| `clients/example_bot.py` | IA d'exemple simple : récolte, dépose, recrute des pions puis des guerriers, attaque. |
| `clients/robot_bot.py` | Le robot adversaire (voir [§19](#19-le-robot-adversaire)). |
| `server/server.py` | Le serveur. |
| `server/map_generator.py` | Le générateur de carte. `py server/map_generator.py 42` affiche dans la console la carte de graine 42. |
| `PROTOCOL.md` | Résumé technique du protocole. |
| `REGLES.md` | Ce document. |

Rien n'impose Python : n'importe quel langage capable d'ouvrir une connexion TCP et de lire ou d'écrire du JSON convient.

---

## 21. Pièges fréquents et FAQ

**Mon IA ne reçoit rien après `join`.** Vérifiez que chaque message se termine par `\n` et que vous videz le tampon d'écriture (`flush`). Vérifiez aussi l'ID de la partie et le port.

**Mes ordres n'ont aucun effet.** Lisez `rejected` dans le message suivant : la raison y est indiquée. Vérifiez aussi que vous renvoyez le bon `turn` (celui du message, pas `state.turn`) et le bon type de réponse (`moves` pour `new_turn`, `actions` pour `action`).

**Mon IA plante et je perds la partie.** Une exception non rattrapée ferme votre programme, donc la connexion, et une déconnexion fait perdre. Entourez votre logique d'un `try / except` et renvoyez une liste vide en cas de problème : le template le fait déjà avec `safe_call`.

**Mon IA est lente.** Au-delà de 5 secondes, vos ordres sont perdus. Une recherche de chemin sur toute la carte pour chaque unité reste rapide en Python (quelques millisecondes), mais les approches lourdes (apprentissage, simulations nombreuses) doivent surveiller leur temps.

**`x` et `y` sont inversés.** La grille s'indexe `grid[y][x]`, mais les positions s'écrivent `[x, y]`.

**Mon pion n'arrive pas à récolter de l'or.** La mine d'or n'est pas marchable : le pion doit se placer **à côté**, diagonales comprises.

**Mon recrutement est refusé alors que j'avais assez de ressources.** Un autre de vos ordres, traité avant, a peut-être déjà dépensé ces ressources. Ou bien le château a déjà recruté ce tour (un seul recrutement par tour). Ou encore aucune case n'est libre autour du château, peut-être parce que vos propres unités l'encerclent.

**Deux de mes unités veulent échanger leurs places.** C'est impossible en un seul tour, car la case d'arrivée doit être libre au moment où le déplacement est traité. Passez par une case intermédiaire.

**Puis-je connaître le chemin exact suivi par une unité ?** Non. Le jeu choisit un plus court chemin, et seules la case de départ et la case d'arrivée sont communiquées. Pour vos calculs, raisonnez sur l'existence d'un chemin d'au plus `move` pas.

**Le hasard intervient-il ?** Uniquement dans la génération de la carte. Les règles sont entièrement déterministes : mêmes ordres et même état donnent le même résultat.

**Y a-t-il un avantage à jouer purple ou yellow ?** Non. La carte est en symétrie centrale, les pions de départ et les recrues sont placés en miroir, et le premier camp traité alterne à chaque tour. Seule une égalité parfaite de deux ordres dans le même tour peut favoriser le camp qui passe en premier ce tour-là.

**Puis-je jouer contre ma propre IA ?** Oui : en mode « Jouer contre un autre joueur / une autre IA », lancez deux fois votre programme avec le même ID.

**Puis-je enchaîner plusieurs parties automatiquement ?** Oui, avec `cours-isen.exe --headless -- --create ...` (voir [§2.2](#22-lancement-automatique-entraînement)). Le serveur accepte plusieurs parties simultanées.

---

## 22. Glossaire français / anglais

| Français | Anglais (dans le protocole) |
|---|---|
| violet / jaune | `purple` / `yellow` |
| pion | `pawn` |
| guerrier | `warrior` |
| lancier | `lancer` |
| archer | `archer` |
| moine | `monk` |
| château | `castle` |
| or / mine d'or | `gold` |
| bois / arbre | `wood` / `tree` |
| viande / mouton | `meat` / `sheep` |
| eau | `water` |
| herbe | `ground` |
| rocher | `rock` |
| points de vie (PV) | `hp`, `max_hp` |
| déplacement | `move` |
| portée | `range` |
| coût | `cost` |
| récolter / déposer / recruter / réparer / attaquer / soigner | `gather` / `deposit` / `recruit` / `repair` / `attack` / `heal` |
| tour | `turn` |
| état | `state` |
| événements | `events` |
| ordres refusés | `rejected` |
| vainqueur / égalité | `winner` / `draw` |
| graine de la carte | `seed` |
