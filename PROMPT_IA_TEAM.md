# Prompts de contexte pour les IA de l'équipe

Pour que chaque membre du groupe soit efficace, il suffit de copier/coller **le contexte de base** suivi de **son rôle spécifique** dans l'invite (prompt) de son IA (ChatGPT, Claude, etc.).

---

## 1. À COPIER PAR TOUT LE MONDE (Le contexte de base)

```text
CONTEXTE DU HACKATHON :
Je participe à un hackathon de 5h pour coder un bot Python (déterministe et très rapide, <5s par tour) pour un jeu de stratégie au tour par tour. 
Nous communiquons avec un serveur TCP en échangeant du JSON.
Le jeu possède une grille 2D. Les déplacements se font en 4 directions (Haut, Bas, Gauche, Droite). Les portées d'attaque, de soin et de récolte se calculent en distance de Chebyshev (les diagonales comptent pour 1).
Il y a 3 ressources inépuisables : 
- Or (coût fixe des unités)
- Viande (le coût augmente à chaque recrutement global de l'équipe)
- Bois (sert uniquement à soigner le château, 1 bois = 1 PV). 
Les Pions récoltent 1 ressource par tour (max 5 d'inventaire) et doivent utiliser l'action 'deposit' à exactement 1 case de distance de notre château pour que les ressources entrent en banque.

Nos unités : Pawn (pion, éco+combat faible), Warrior (mêlée), Lancer (portée 2), Archer (portée 4), Monk (soigne portée 2).

Notre architecture est une **Utility AI** :
1. Analyse Macro : on calcule les menaces, notre ratio militaire et notre économie pour définir un "État" (Développement, Défense, etc.).
2. L'état modifie les poids (multiplicateurs) des actions.
3. Micro Scoring : on génère toutes les actions légales pour chaque unité, et on leur attribue un score de désirabilité.
4. Focus Fire : on garde en mémoire les PV virtuels des ennemis ciblés ce tour-ci. Si les attaques prévues suffisent à tuer une cible, le score pour l'attaquer tombe à 0 pour nos unités suivantes (pour éviter le gaspillage de dégâts).
5. Économie : L'ordre final du tableau JSON d'actions est strictement structuré pour la résolution serveur : 'deposit' en premier, puis 'recruit/repair', puis les autres actions.
```

---

## 2. AJOUTS PAR RÔLE (À copier à la suite du contexte de base)

### Rôle : Le Cartographe (Pathfinding & Grille)
```text
MON RÔLE : LE CARTOGRAPHE
Je m'occupe de la grille et des déplacements (ex: fichier `pathfinding.py`). 
Ma mission :
- Coder un algorithme de recherche de chemin (BFS ou A*) très performant. Les déplacements sont en 4 directions. Les cases marchables sont : l'herbe nue ('ground'), les arbres ('tree') et les moutons ('sheep'). Le reste (eau, rochers, mines d'or, châteaux) bloque les déplacements.
- Coder les utilitaires : `get_chebyshev_distance(p1, p2)`, `get_walkable_neighbors(pos)`.
- Créer une fonction appelée au tour 1 pour lister et trier les ressources de la carte selon leur proximité avec notre château.
Prépare-toi à m'aider à coder ces algorithmes en optimisant la performance.
```

### Rôle : Le Général (Macro & Machine à États)
```text
MON RÔLE : LE GÉNÉRAL
Je m'occupe de la prise de décision globale (ex: fichier `macro.py`).
Ma mission :
- Extraire à chaque tour des métriques globales depuis l'objet JSON (PV de notre château, coût actuel de la viande 'next_meat_cost', ratio entre la somme des dégâts de mon armée et celle de l'ennemi, distance de l'ennemi le plus proche).
- Coder la Machine à États qui prend ces métriques et renvoie notre stratégie du tour (ex: 'ECO_FOCUS', 'DEFENSE_URGENTE', 'ASSAUT').
- Définir un dictionnaire de multiplicateurs : pour chaque État, on renvoie les multiplicateurs de score (ex: En DEFENSE_URGENTE, le multiplicateur de l'action "attaquer" fait x5).
Prépare-toi à concevoir avec moi cette structure d'analyse globale.
```

### Rôle : Le Tacticien (Micro & Utility Scoring)
```text
MON RÔLE : LE TACTICIEN
Je m'occupe des actions individuelles des unités (ex: fichier `micro.py`).
Ma mission :
- Pour chaque unité de mon équipe, générer la liste de toutes ses actions possibles (attack cible_X, heal cible_Y, gather cible_Z).
- Appliquer la formule de l'Utility AI : Score_Final = Score_Base_Action * Multiplicateur_Macro.
- IMPÉRATIF : Implémenter le "Virtual HP Tracker". On doit maintenir un dictionnaire des PV restants simulés des ennemis ce tour-ci. Si on attribue une attaque à une unité qui tue un ennemi, l'ennemi a 0 PV virtuel. Les unités alliées suivantes évalueront l'attaque sur cet ennemi avec un score de 0.
Prépare-toi à m'aider à coder cette logique d'évaluation et de Focus Fire.
```

### Rôle : Le Logisticien (Économie & Recrutement)
```text
MON RÔLE : LE LOGISTICIEN
Je m'occupe du château, de l'économie et de la résolution (ex: fichier `economy.py`).
Ma mission :
- Gérer la décision du château (1 action 'recruit' max par tour). Choisir quoi recruter selon les stocks actuels (Or et Viande), le coût grandissant de la viande, et l'État Macro demandé par Le Général.
- Gérer l'action 'repair' : elle consomme tout le bois en un coup (1 bois = 1 PV). Implémenter une règle pour ne réparer que si notre stock de bois <= PV manquants du château (pour zéro gaspillage).
- Écrire la fonction de tri vitale : elle doit prendre la liste finale de toutes les actions du tour et la trier pour que les objets JSON de type 'deposit' soient en premier, suivis des 'recruit' / 'repair', et enfin les autres actions.
Prépare-toi à m'aider à coder ces règles économiques.
```
