"""
map_utils.py — fonctions utilitaires « carte / distances / chemins ».

Principe
--------
Toutes les fonctions travaillent directement sur le JSON `state` reçu du serveur
(messages `new_turn` et `action`). Il n'y a rien à construire ni à initialiser.

Conventions (à connaître avant d'utiliser le module)
----------------------------------------------------
* Une position est un tuple ``(x, y)`` : ``x`` = colonne, ``y`` = ligne (l'axe y pointe vers le BAS).
* La grille s'indexe ``state["grid"][y][x]`` (ligne d'abord) alors que les positions s'écrivent ``(x, y)``.
* Un « rect » est soit un dict château de ``state["buildings"]`` (clés x, y, width, height),
  soit un tuple ``(x, y, largeur, hauteur)`` avec (x, y) = coin haut-gauche.
  Un point seul se décrit par ``(x, y, 1, 1)``.
* Deux distances à ne pas confondre :
    - PORTÉE (attaque, soin, récolte, dépôt) -> distance de Chebyshev, diagonales = 1.
    - DÉPLACEMENT -> pas en 4 directions (haut/bas/gauche/droite), obstacles contournés.
* Terrain marchable par défaut : codes 1 (ground), 4 (tree), 5 (sheep).
  La mine d'or (3), l'eau (0), les rochers (2) et les châteaux (6, 7) ne sont PAS marchables.
  Pour lire les codes dans `rules` plutôt que de se fier au défaut : ``walkable=walkable_codes(rules)``.
* Les unités ne sont pas dans `grid` : elles sont gérées à part avec `blocked` / `occupied` :
    - `blocked`  = positions que le chemin ne peut pas traverser (unités ENNEMIES) ;
    - `occupied` = positions où l'on ne peut pas S'ARRÊTER (TOUTES les unités, alliées comprises).
  Nos propres unités sont traversables, mais pas utilisables comme case d'arrivée.
"""

from collections import deque
from typing import Any, Deque, Dict, Iterable, List, Optional, Set, Tuple, TypedDict, Union

# ============================================================================
# Types
# ============================================================================

Pos = Tuple[int, int]                       # (x, y)
State = Dict[str, Any]                      # le JSON `state` du serveur
Rules = Dict[str, Any]                      # le JSON `rules` de game_start
Unit = Dict[str, Any]                       # un élément de state["units"]
Building = Dict[str, Any]                   # un élément de state["buildings"] (le château)
Rect = Union[Building, Tuple[int, int, int, int]]   # château (dict) ou (x, y, largeur, hauteur)
Field = Dict[Pos, int]                      # champ de distance : position -> nombre de pas jusqu'au but
Walkable = Union[Set[int], frozenset]       # ensemble de codes de terrain marchables


class ResourceInfo(TypedDict):
    """Un gisement vu depuis notre château (résultat de `sorted_resources`)."""
    pos: Pos          # position du gisement
    resource: str     # "gold" | "wood" | "meat"
    cheb: int         # distance de Chebyshev au château
    steps: int        # pas à pied entre une case de dépôt et la meilleure case de récolte (INF si inaccessible)
    spot: Optional[Pos]   # meilleure case où se placer pour récolter (None si inaccessible)


INF: int = 10 ** 9                               # « infini » : inaccessible
WALKABLE: frozenset = frozenset({1, 4, 5})       # ground, tree, sheep
_LEGEND: List[str] = ["water", "ground", "rock", "gold", "tree", "sheep", "castle_purple", "castle_yellow"]


# ============================================================================
# 1. Distances
# ============================================================================

def get_distance_chebyshev(a: Pos, b: Pos) -> int:
    """Distance de Chebyshev entre deux positions : ``max(|dx|, |dy|)``.

    C'est la distance utilisée pour toutes les PORTÉES du jeu (attaque, soin, récolte, dépôt).
    Les 8 cases autour d'une unité sont à distance 1.

    Exemple : ``get_distance_chebyshev((10, 10), (11, 11)) == 1``
    (mais il faut 2 pas à pied pour y aller : voir `path_length`).
    """
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _rect(r: Rect) -> Tuple[int, int, int, int]:
    """(interne) Normalise un château/rect en tuple (x, y, largeur, hauteur)."""
    if isinstance(r, dict):
        return r["x"], r["y"], r["width"], r["height"]
    return tuple(r)  # type: ignore[return-value]


def dist_to_rect(pos: Pos, rect: Rect) -> int:
    """Distance de Chebyshev entre `pos` et la case la plus PROCHE d'un château (ou rect).

    C'est la règle du jeu pour attaquer, déposer, etc. un bâtiment qui occupe plusieurs cases.
    Retourne 0 si `pos` est dans le rectangle.

    Exemple : pour un château en (27, 27, 4, 2), ``dist_to_rect((24, 27), château) == 3``.
    """
    rx, ry, rw, rh = _rect(rect)
    dx = max(rx - pos[0], 0, pos[0] - (rx + rw - 1))
    dy = max(ry - pos[1], 0, pos[1] - (ry + rh - 1))
    return max(dx, dy)


def in_range(pos: Pos, target: Pos, reach: int) -> bool:
    """Vrai si `target` est à portée (Chebyshev <= `reach`) depuis `pos`.

    Pour une cible qui est un château, utiliser plutôt ``dist_to_rect(pos, château) <= reach``.
    """
    return get_distance_chebyshev(pos, target) <= reach


# ============================================================================
# 2. Terrain et voisinage
# ============================================================================

def walkable_codes(rules: Rules) -> frozenset:
    """Codes de terrain marchables, lus dans `rules` (robuste si les règles changent).

    Utilise `rules["legend"]` (nom de chaque code) et `rules["walkable"]` (noms marchables).

    Exemple : ``w = walkable_codes(rules)`` puis ``is_walkable(state, pos, w)``.
    """
    legend = rules.get("legend", _LEGEND)
    names = set(rules.get("walkable", ["ground", "tree", "sheep"]))
    return frozenset(i for i, n in enumerate(legend) if n in names)


def in_bounds(state: State, pos: Pos) -> bool:
    """Vrai si `pos` est une case de la carte (0 <= x < width et 0 <= y < height)."""
    return 0 <= pos[0] < state["width"] and 0 <= pos[1] < state["height"]


def is_walkable(state: State, pos: Pos, walkable: Walkable = WALKABLE) -> bool:
    """Vrai si le TERRAIN de `pos` est marchable (hors carte -> faux).

    Attention : ne regarde pas les unités. Une case marchable peut être occupée ;
    pour savoir si on peut s'y arrêter, tester aussi ``pos not in occupied``.
    """
    return in_bounds(state, pos) and state["grid"][pos[1]][pos[0]] in walkable


def get_neighbors(state: State, pos: Pos, walkable: Walkable = WALKABLE) -> List[Pos]:
    """Voisins MARCHABLES en 4 directions (haut, bas, gauche, droite) : ce sont les pas de déplacement.

    Exemple : ``get_neighbors(state, (10, 10))`` -> ``[(10, 9), (10, 11), (9, 10), (11, 10)]``
    (moins les cases d'eau, rochers, etc.).
    """
    x, y = pos
    return [p for p in ((x, y - 1), (x, y + 1), (x - 1, y), (x + 1, y)) if is_walkable(state, p, walkable)]


def get_neighbors8(state: State, pos: Pos, walkable: Walkable = WALKABLE) -> List[Pos]:
    """Les 8 cases voisines marchables (diagonales comprises) = toutes les cases à portée 1.

    Utile pour savoir où se placer à côté d'un gisement ou d'une cible.
    Ce n'est PAS un voisinage de déplacement (voir `get_neighbors`).
    """
    x, y = pos
    return [(x + dx, y + dy) for dy in (-1, 0, 1) for dx in (-1, 0, 1)
            if (dx or dy) and is_walkable(state, (x + dx, y + dy), walkable)]


def cells_within(state: State, rect: Rect, reach: int, walkable: Walkable = WALKABLE) -> List[Pos]:
    """Cases marchables situées à distance de Chebyshev <= `reach` d'un rect.

    Répond à la question « d'où puis-je agir sur cet objet ? » :
      * récolter un gisement      : ``cells_within(state, (x, y, 1, 1), 1)``
      * déposer au château        : ``cells_within(state, château, 1)``
      * tirer sur le château ennemi avec un archer : ``cells_within(state, château_ennemi, 4)``

    Ne tient pas compte des unités présentes. Pour un gisement marchable (arbre, mouton),
    sa propre case fait partie du résultat.
    """
    x, y, w, h = _rect(rect)
    grid = state["grid"]
    return [(cx, cy)
            for cy in range(max(0, y - reach), min(state["height"] - 1, y + h - 1 + reach) + 1)
            for cx in range(max(0, x - reach), min(state["width"] - 1, x + w - 1 + reach) + 1)
            if grid[cy][cx] in walkable]


# ============================================================================
# 3. Accès à l'état (raccourcis)
# ============================================================================

def my_castle(state: State, team: str) -> Optional[Building]:
    """Notre château (dict de `state["buildings"]`), ou None s'il est détruit."""
    return next((b for b in state["buildings"] if b["team"] == team), None)


def enemy_castle(state: State, team: str) -> Optional[Building]:
    """Le château adverse (dict de `state["buildings"]`), ou None s'il est détruit."""
    return next((b for b in state["buildings"] if b["team"] != team), None)


def my_units(state: State, team: str) -> List[Unit]:
    """Toutes nos unités vivantes."""
    return [u for u in state["units"] if u["team"] == team]


def enemy_units(state: State, team: str) -> List[Unit]:
    """Toutes les unités ennemies vivantes (l'information est complète, pas de brouillard)."""
    return [u for u in state["units"] if u["team"] != team]


def unit_positions(state: State, team: Optional[str] = None, enemy_of: Optional[str] = None) -> Set[Pos]:
    """Ensemble des positions occupées par des unités.

    * ``unit_positions(state)``                    -> toutes les unités (= `occupied`)
    * ``unit_positions(state, team="purple")``     -> uniquement celles de purple
    * ``unit_positions(state, enemy_of="purple")`` -> uniquement les ennemies de purple (= `blocked`)
    """
    return {(u["x"], u["y"]) for u in state["units"]
            if (team is None or u["team"] == team) and (enemy_of is None or u["team"] != enemy_of)}


# ============================================================================
# 4. Chemins (BFS, 4 directions)
# ============================================================================

def bfs_distances(state: State, sources: Iterable[Pos], blocked: Optional[Set[Pos]] = None,
                  walkable: Walkable = WALKABLE, max_depth: Optional[int] = None) -> Field:
    """Parcours en largeur (BFS) multi-sources, en 4 directions, sur tout le terrain marchable.

    Args:
        sources:   une ou plusieurs cases de départ (distance 0).
        blocked:   positions infranchissables en plus du terrain (typiquement les unités ennemies).
        max_depth: si donné, on ne dépasse pas ce nombre de pas (plus rapide).

    Returns:
        ``{position: nombre de pas minimal depuis la source la plus proche}``.
        Une case absente du dict est inaccessible (ou trop loin si `max_depth`).

    Exemple : ``bfs_distances(state, [(10, 10)])[(14, 10)]`` -> ``4`` si la voie est libre.
    """
    grid, W, H = state["grid"], state["width"], state["height"]
    blocked = blocked or set()
    dist: Field = {}
    dq: Deque[Pos] = deque()
    for s in sources:
        s = (s[0], s[1])
        if in_bounds(state, s) and grid[s[1]][s[0]] in walkable and s not in dist:
            dist[s] = 0
            dq.append(s)
    while dq:
        p = dq.popleft()
        d = dist[p] + 1
        if max_depth is not None and d > max_depth:
            continue
        x, y = p
        for q in ((x, y - 1), (x, y + 1), (x - 1, y), (x + 1, y)):
            if q not in dist and 0 <= q[0] < W and 0 <= q[1] < H \
                    and grid[q[1]][q[0]] in walkable and q not in blocked:
                dist[q] = d
                dq.append(q)
    return dist


def reachable(state: State, start: Pos, max_steps: int, blocked: Optional[Set[Pos]] = None,
              walkable: Walkable = WALKABLE) -> Field:
    """Toutes les cases atteignables depuis `start` en au plus `max_steps` pas.

    Args:
        max_steps: le `move` de l'unité (``rules["units"][type]["move"]``).
        blocked:   unités ennemies (non traversables).

    Returns:
        ``{position: nombre de pas}``, `start` inclus (0 pas).

    Attention : le résultat contient aussi des cases occupées par nos unités (traversables mais
    pas utilisables comme arrivée) : filtrer avec `occupied` avant de choisir une destination.
    """
    return bfs_distances(state, [start], blocked, walkable, max_steps)


def shortest_path(state: State, start: Pos, goal: Pos, blocked: Optional[Set[Pos]] = None,
                  walkable: Walkable = WALKABLE, max_steps: Optional[int] = None) -> Optional[List[Pos]]:
    """Plus court chemin en 4 directions de `start` à `goal`, ou None s'il n'y en a pas.

    Args:
        blocked:   unités ennemies (on les contourne).
        max_steps: abandonne (None) si le chemin dépasse cette longueur.

    Returns:
        ``[start, ..., goal]`` (le nombre de pas est ``len(chemin) - 1``).

    Note : le jeu calcule lui-même le chemin réel ; ici, on s'en sert pour estimer des durées
    ou vérifier qu'un trajet existe. Pour guider plusieurs unités vers un même but, préférer
    `goal_field` + `step_toward`, bien plus rapide.
    """
    start, goal = (start[0], start[1]), (goal[0], goal[1])
    if not (is_walkable(state, start, walkable) and is_walkable(state, goal, walkable)):
        return None
    if start == goal:
        return [start]
    blocked = blocked or set()
    if goal in blocked:
        return None
    parent: Dict[Pos, Optional[Pos]] = {start: None}
    frontier: List[Pos] = [start]
    depth = 0
    while frontier:
        depth += 1
        if max_steps is not None and depth > max_steps:
            return None
        nxt: List[Pos] = []
        for p in frontier:
            for q in get_neighbors(state, p, walkable):
                if q not in parent and q not in blocked:
                    parent[q] = p
                    if q == goal:
                        path = [q]
                        while parent[path[-1]] is not None:
                            path.append(parent[path[-1]])  # type: ignore[arg-type]
                        return path[::-1]
                    nxt.append(q)
        frontier = nxt
    return None


def path_length(state: State, start: Pos, goal: Pos, blocked: Optional[Set[Pos]] = None,
                walkable: Walkable = WALKABLE) -> int:
    """Nombre de pas du plus court chemin de `start` à `goal`, ou `INF` s'il n'existe pas."""
    p = shortest_path(state, start, goal, blocked, walkable)
    return INF if p is None else len(p) - 1


# ============================================================================
# 5. Déplacer les unités
# ============================================================================

def move_order(unit_id: int, pos: Pos) -> Dict[str, Any]:
    """Construit l'ordre JSON à mettre dans la liste `moves`.

    Exemple : ``move_order(7, (31, 24))`` -> ``{"unit": 7, "to": [31, 24]}``
    """
    return {"unit": unit_id, "to": [int(pos[0]), int(pos[1])]}


def goal_field(state: State, goal_cells: Iterable[Pos], walkable: Walkable = WALKABLE) -> Field:
    """Champ de distance (en pas à pied) vers un ensemble de cases but.

    À calculer UNE SEULE FOIS par but, puis à passer à `step_toward` pour chaque unité
    qui vise ce but (ex. tous les pions qui vont à la même mine).

    Exemples de `goal_cells` :
      * aller récolter : ``cells_within(state, (x, y, 1, 1), 1)``
      * aller déposer  : ``cells_within(state, my_castle(state, team), 1)``
      * assaut         : ``cells_within(state, enemy_castle(state, team), portée_de_l_unité)``

    Le champ ignore les unités (terrain seul) : c'est `step_toward` qui gère les obstacles mobiles.
    """
    return bfs_distances(state, goal_cells, None, walkable)


def step_toward(state: State, unit: Unit, move: int, field: Field,
                enemy_pos: Optional[Set[Pos]] = None, occupied: Optional[Set[Pos]] = None,
                walkable: Walkable = WALKABLE) -> Pos:
    """Choisit la meilleure case d'arrivée de `unit` ce tour pour se rapprocher d'un but.

    Args:
        unit:      dict de ``state["units"]`` (utilise ses clés x et y).
        move:      pas maximum de l'unité (``rules["units"][unit["type"]]["move"]``).
        field:     résultat de `goal_field` pour le but visé.
        enemy_pos: positions ennemies, non traversables (``unit_positions(state, enemy_of=team)``).
        occupied:  toutes les unités : on ne peut pas s'y arrêter (``unit_positions(state)``).
                   À METTRE À JOUR après chaque ordre (retirer l'ancienne position, ajouter la nouvelle),
                   et l'ordre de vos `moves` doit suivre l'ordre de vos appels.

    Returns:
        La position d'arrivée, ou la position actuelle si l'unité ne peut pas se rapprocher
        (déjà sur le but, ou bloquée). À ne transformer en ordre que si elle diffère de la position actuelle.

    En cas d'égalité entre deux cases, on prend celle qui demande le moins de pas.
    """
    start = (unit["x"], unit["y"])
    occupied = occupied or set()
    best, best_key = start, (field.get(start, INF), 0)
    for pos, steps in reachable(state, start, move, enemy_pos, walkable).items():
        if pos == start or pos in occupied:
            continue
        key = (field.get(pos, INF), steps)
        if key < best_key:
            best, best_key = pos, key
    return best


# ============================================================================
# 6. Ressources
# ============================================================================

def sorted_resources(state: State, team: str, kind: Optional[str] = None,
                     walkable: Walkable = WALKABLE) -> List[ResourceInfo]:
    """Gisements triés du plus proche au plus loin de NOTRE château.

    Tri : d'abord `steps` (distance à pied réelle entre le dépôt et la case de récolte),
    puis `cheb` (Chebyshev). Les gisements inaccessibles (`steps == INF`) sont en fin de liste.

    Args:
        kind: ``"gold"``, ``"wood"``, ``"meat"`` ou None pour tous.

    Returns:
        Liste de `ResourceInfo`. Pour récolter, envoyer le pion sur ``spot`` puis ``gather`` sur ``pos``.

    Les gisements ne bougent jamais ni ne s'épuisent : calcul à faire une seule fois.
    Préférer `get_sorted_resources`, qui met le résultat en cache.
    """
    castle = my_castle(state, team)
    field = bfs_distances(state, cells_within(state, castle, 1, walkable), None, walkable)
    out: List[ResourceInfo] = []
    for r in state["resources"]:
        if kind is not None and r["resource"] != kind:
            continue
        pos = (r["x"], r["y"])
        spot: Optional[Pos] = None
        best = INF
        for sp in cells_within(state, (pos[0], pos[1], 1, 1), 1, walkable):
            v = field.get(sp, INF)
            if v < best:
                best, spot = v, sp
        out.append({"pos": pos, "resource": r["resource"], "cheb": dist_to_rect(pos, castle),
                    "steps": best, "spot": spot})
    out.sort(key=lambda r: (r["steps"], r["cheb"]))
    return out


_RES_CACHE: Dict[str, List[ResourceInfo]] = {}


def get_sorted_resources(state: State, team: str, kind: Optional[str] = None) -> List[ResourceInfo]:
    """Comme `sorted_resources`, mais calculé au premier appel (tour 1) puis réutilisé.

    À privilégier dans le bot : les gisements sont fixes pendant toute la partie.
    Le cache est indexé par camp ; il faut relancer le programme pour une nouvelle partie.

    Exemple : ``get_sorted_resources(state, team, "gold")[0]["spot"]`` = case où envoyer le premier pion.
    """
    if team not in _RES_CACHE:
        _RES_CACHE[team] = sorted_resources(state, team)
    res = _RES_CACHE[team]
    return res if kind is None else [r for r in res if r["resource"] == kind]


def expected_income(steps: int, move: int = 4, capacity: int = 5) -> float:
    """Revenu estimé, en unités par tour, d'un pion dont le gisement est à `steps` pas du dépôt.

    Formule du §18.2 des règles : aller + (capacity - 1) récoltes + retour, au minimum capacity + 1 tours.
    Exemples : 4 pas -> ~0.83 ; 12 pas -> 0.5. Sert à comparer deux gisements.
    """
    trip = -(-steps // move) if steps > 0 else 0          # division arrondie au supérieur
    return capacity / max(2 * trip + capacity - 1, capacity + 1)


# ============================================================================
# Test rapide : `python map_utils.py`
# ============================================================================

if __name__ == "__main__":
    import random
    import time

    rnd = random.Random(1)
    W, H = 80, 74
    grid = [[0 if x < 8 or y < 8 or x >= W - 8 or y >= H - 8 else 1 for x in range(W)] for y in range(H)]
    for _ in range(200):
        grid[rnd.randrange(8, H - 8)][rnd.randrange(8, W - 8)] = rnd.choice([0, 2, 3, 4, 5])
    for (cx, cy), code in (((27, 27), 6), ((49, 45), 7)):
        for dy in range(2):
            for dx in range(4):
                grid[cy + dy][cx + dx] = code
    names = {3: "gold", 4: "wood", 5: "meat"}
    state: State = {
        "width": W, "height": H, "grid": grid,
        "resources": [{"x": x, "y": y, "resource": names[grid[y][x]]}
                      for y in range(H) for x in range(W) if grid[y][x] in names],
        "buildings": [{"id": 1, "team": "purple", "x": 27, "y": 27, "width": 4, "height": 2},
                      {"id": 2, "team": "yellow", "x": 49, "y": 45, "width": 4, "height": 2}],
        "units": [{"id": 3, "team": "purple", "type": "pawn", "x": 25, "y": 26},
                  {"id": 6, "team": "yellow", "type": "pawn", "x": 50, "y": 44}],
    }

    assert get_distance_chebyshev((10, 10), (11, 11)) == 1
    assert dist_to_rect((24, 27), (27, 27, 4, 2)) == 3
    assert not is_walkable(state, (27, 27)) and not is_walkable(state, (-1, 0))

    t = time.perf_counter()
    res = get_sorted_resources(state, "purple", "gold")
    print("or le plus proche :", res[0], f"({(time.perf_counter() - t) * 1000:.1f} ms)")

    u = state["units"][0]
    field = goal_field(state, cells_within(state, (res[0]["pos"][0], res[0]["pos"][1], 1, 1), 1))
    t = time.perf_counter()
    for _ in range(40):
        dest = step_toward(state, u, 4, field, unit_positions(state, enemy_of="purple"), unit_positions(state))
    print("40 x step_toward :", f"{(time.perf_counter() - t) * 1000:.1f} ms", "->", move_order(u["id"], dest))

    p = shortest_path(state, (25, 26), (52, 50), unit_positions(state, enemy_of="purple"))
    print("chemin base->base :", None if p is None else len(p) - 1, "pas")
    if p:
        assert all(abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1 and is_walkable(state, b) for a, b in zip(p, p[1:]))
    print("OK")
