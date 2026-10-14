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
                walkable: Walkable = WALKABLE, sidestep: bool = False,
                avoid: Optional[Pos] = None) -> Pos:
    """Choisit la meilleure case d'arrivée de `unit` ce tour pour se rapprocher d'un but.

    Args:
        unit:      dict de ``state["units"]`` (utilise ses clés x et y).
        move:      pas maximum de l'unité (``rules["units"][unit["type"]]["move"]``).
        field:     résultat de `goal_field` (ou de `Goal.field_for`) pour le but visé.
        enemy_pos: positions ennemies, non traversables (``unit_positions(state, enemy_of=team)``).
        occupied:  toutes les unités : on ne peut pas s'y arrêter (``unit_positions(state)``).
                   À METTRE À JOUR après chaque ordre (retirer l'ancienne position, ajouter la nouvelle),
                   et l'ordre de vos `moves` doit suivre l'ordre de vos appels.
        sidestep:  si vrai et que l'unité est BLOQUÉE (aucune case libre ne la rapproche, typiquement
                   parce que ses alliés occupent toutes les cases devant elle), elle fait un pas
                   latéral vers une case libre de même distance pour contourner l'embouteillage.
        avoid:     case à ne pas reprendre lors d'un pas latéral (la case quittée au tour précédent),
                   pour éviter les allers-retours.

    Returns:
        La position d'arrivée, ou la position actuelle si l'unité ne peut pas se rapprocher
        (déjà sur le but, ou bloquée). À ne transformer en ordre que si elle diffère de la position actuelle.

    En cas d'égalité entre deux cases, on prend celle qui demande le moins de pas.
    """
    start = (unit["x"], unit["y"])
    occupied = occupied or set()
    start_val = field.get(start, INF)
    best, best_key = start, (start_val, 0)
    reach = reachable(state, start, move, enemy_pos, walkable)
    for pos, steps in reach.items():
        if pos == start or pos in occupied:
            continue
        key = (field.get(pos, INF), steps)
        if key < best_key:
            best, best_key = pos, key
    # Bloquée loin du but (>1) : pas latéral plutôt que de rester plantée derrière ses alliés.
    if best == start and sidestep and 1 < start_val < INF:
        side = [(steps, pos) for pos, steps in reach.items()
                if pos != start and pos != avoid and pos not in occupied
                and field.get(pos, INF) <= start_val]
        if side:
            best = min(side)[1]
    return best


class Goal:
    """But PARTAGÉ par plusieurs unités : un ensemble de cases d'où l'on peut agir.

    Problème résolu : si 10 unités visent les mêmes cases (autour d'un château, d'une mine…),
    les premières les occupent et les suivantes restent bloquées derrière, car leur champ de
    distance pointe toujours vers des cases déjà prises. Ici, le champ est calculé uniquement
    vers les cases LIBRES (non occupées) et recalculé quand elles changent ; s'il n'y en a plus,
    on se rabat sur toutes les cases (l'unité s'approche et attend).

    Usage ::

        g = Goal(state, cells_within(state, château_ennemi, reach))
        if (u["x"], u["y"]) not in g.cellset:                  # pas déjà en place
            f = g.field_for(occupied)
            dest = step_toward(state, u, move, f, enemy_pos, occupied, sidestep=True)
    """

    def __init__(self, state: State, cells: Iterable[Pos], walkable: Walkable = WALKABLE) -> None:
        self.state = state
        self.walkable = walkable
        self.cells: List[Pos] = list(cells)
        self.cellset: Set[Pos] = set(self.cells)
        self._cache: Dict[Any, Field] = {}

    def has_free_cell(self, occupied: Set[Pos]) -> bool:
        """Vrai s'il reste au moins une case but non occupée."""
        return any(c not in occupied for c in self.cells)

    def field_for(self, occupied: Set[Pos], pos: Optional[Pos] = None) -> Field:
        """Champ de distance vers les cases but libres (ou vers toutes si aucune n'est libre).

        Les unités DÉJÀ EN PLACE sur une case but ne bougeront plus : le champ les contourne
        (sinon une unité lente, qui ne peut pas traverser ses alliés, serait guidée « à travers »
        la rangée de ses camarades et resterait coincée derrière).
        Si `pos` est donné et que le contournement le coupe du but, on retombe sur le champ sans obstacle.
        """
        free = frozenset(c for c in self.cells if c not in occupied)
        if not free:
            free = frozenset(self.cells)
        blocked = frozenset(self.cellset - free)
        key = (free, blocked)
        f = self._cache.get(key)
        if f is None:
            f = goal_field(self.state, free, self.walkable) if not blocked else \
                bfs_distances(self.state, free, set(blocked), self.walkable)
            self._cache[key] = f
        if pos is not None and blocked and pos not in f:
            return self.field_for_plain(free)
        return f

    def field_for_plain(self, free: frozenset) -> Field:
        """Champ sans aucun obstacle vers les cases `free` (repli)."""
        key = (free, None)
        f = self._cache.get(key)
        if f is None:
            f = goal_field(self.state, free, self.walkable)
            self._cache[key] = f
        return f


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
# 7. Interface du bot (init_map et get_moves)
# ============================================================================

# Mémoire de la case quittée au tour précédent, par unité (anti aller-retour des pas latéraux).
_PREV: Dict[int, Pos] = {}


def init_map(state: State, rules: Rules) -> None:
    """Initialise le cache de la carte et des ressources (à appeler au début de chaque partie)."""
    _RES_CACHE.clear()
    _PREV.clear()


def get_moves(state: State, rules: Rules, team: str) -> List[Dict[str, Any]]:
    """
    Calcule tous les déplacements du tour pour les unités de notre camp.

    Anti-blocage :
      * chaque but est un `Goal` : les cases déjà occupées ne sont plus visées, donc les unités
        suivantes se répartissent sur les cases libres au lieu de s'empiler derrière les premières ;
      * les unités sont traitées de l'AVANT vers l'ARRIÈRE (les plus proches de l'ennemi d'abord) :
        une case libérée par une unité de tête est immédiatement utilisable par celles de derrière ;
      * une unité bloquée par ses alliés fait un pas latéral au lieu de rester plantée ;
      * l'aire d'attente est à 2-4 cases du château (et non collée à lui) : l'anneau de dépôt et les
        cases de recrutement restent libres ;
      * un pion choisit un gisement qui a encore de la place autour.

    Anti « ne tape pas alors qu'il est à portée » :
      * un combattant qui a déjà un ennemi à portée NE BOUGE PLUS (il attaquera) au lieu de
        poursuivre sa marche et de sortir de portée.
    """
    import macro

    castle = my_castle(state, team)
    e_castle = enemy_castle(state, team)
    if not castle:
        return []

    # Positions occupées par toutes les unités et par les ennemis (bloquants)
    occupied = set(unit_positions(state))
    enemy_pos = set(unit_positions(state, enemy_of=team))

    # Stratégie macro
    macro_state = macro.analyze_state(state, rules, team)

    # Ressources triées par proximité
    gold_res = get_sorted_resources(state, team, "gold")
    meat_res = get_sorted_resources(state, team, "meat")
    wood_res = get_sorted_resources(state, team, "wood")

    bank = state["teams"][team]["resources"]
    next_meat = state["teams"][team]["next_meat_cost"]

    moves: List[Dict[str, Any]] = []

    # Règles par défaut si non fournies
    default_moves = {"pawn": 4, "warrior": 3, "lancer": 2, "archer": 1, "monk": 1}
    default_ranges = {"pawn": 1, "warrior": 1, "lancer": 2, "archer": 4, "monk": 2}
    unit_stats = rules.get("units", {}) if rules else {}

    all_my_units = my_units(state, team)
    enemies = enemy_units(state, team)
    enemy_xy = [(e["x"], e["y"]) for e in enemies]
    my_pawns = [p for p in all_my_units if p["type"] == "pawn"]
    military_units = [m for m in all_my_units if m["type"] in ("warrior", "lancer", "archer")]
    cur_pos: Dict[int, Pos] = {m["id"]: (m["x"], m["y"]) for m in all_my_units}   # positions à jour

    # ---------------------------------------------------------------- buts partagés
    goals: Dict[Any, Goal] = {}

    def goal_around(rect: Rect, reach: int) -> Goal:
        """But = cases marchables à portée `reach` de `rect` (partagé entre toutes les unités du tour)."""
        r = _rect(rect)
        key = (r, reach)
        g = goals.get(key)
        if g is None:
            g = goals[key] = Goal(state, cells_within(state, r, reach))
        return g

    def staging_goal() -> Goal:
        """Aire d'attente à 2-4 cases du château, côté ennemi. Laisse libres les cases collées au château."""
        g = goals.get("staging")
        if g is None:
            cells = [c for c in cells_within(state, castle, 4) if dist_to_rect(c, castle) >= 2]
            if e_castle:
                cells.sort(key=lambda c: (dist_to_rect(c, e_castle), c))
            g = goals["staging"] = Goal(state, cells[:40])
        return g

    def go(u: Unit, g: Goal, max_move: int) -> Pos:
        """Un pas vers le but `g` (ne bouge pas si déjà en place)."""
        pos = (u["x"], u["y"])
        if pos in g.cellset or not g.cells:
            return pos
        return step_toward(state, u, max_move, g.field_for(occupied, pos), enemy_pos, occupied,
                           sidestep=True, avoid=_PREV.get(u["id"]))

    def best_source(lst: List[ResourceInfo], pos: Pos) -> Optional[ResourceInfo]:
        """Gisement le plus proche qui a encore une case libre autour (sinon le plus proche)."""
        for r in lst:
            g = goal_around((r["pos"][0], r["pos"][1], 1, 1), 1)
            if pos in g.cellset or g.has_free_cell(occupied):
                return r
        return lst[0] if lst else None

    def enemy_unit_in_range(p: Pos, r: int) -> bool:
        return any(get_distance_chebyshev(p, q) <= r for q in enemy_xy)

    def castle_in_range(p: Pos, r: int) -> bool:
        return bool(e_castle) and dist_to_rect(p, e_castle) <= r

    def front_dist(u: Unit) -> int:
        p = (u["x"], u["y"])
        d = min((get_distance_chebyshev(p, q) for q in enemy_xy), default=INF)
        if e_castle:
            d = min(d, dist_to_rect(p, e_castle))
        return d

    # Ordre de traitement : combattants (les plus avancés d'abord), puis moines, puis pions.
    def order_key(u: Unit) -> Tuple[int, int, int]:
        t = u["type"]
        if t == "pawn":
            return (2, 0, u["id"])
        if t == "monk":
            return (1, front_dist(u), u["id"])
        return (0, front_dist(u), u["id"])

    for u in sorted(all_my_units, key=order_key):
        if u.get("hp", 0) <= 0:
            continue

        u_id = u["id"]
        u_type = u["type"]
        pos = (u["x"], u["y"])
        max_move = unit_stats.get(u_type, {}).get("move", default_moves.get(u_type, 1))
        reach = unit_stats.get(u_type, {}).get("range", default_ranges.get(u_type, 1))

        dest = pos

        # --- Comportement des Pions (Pawn) ---
        if u_type == "pawn":
            carrying = u.get("carrying")
            amount = carrying["amount"] if carrying else 0
            res_type = carrying["resource"] if carrying else None

            # Si plein ou presque plein, ou transportant des ressources près du château -> Déposer
            dist_c = dist_to_rect(pos, castle)
            should_deposit = (amount >= 5) or (amount > 0 and (dist_c <= 2 or macro_state == "DEFENSE_URGENTE"))

            if should_deposit:
                dest = go(u, goal_around(castle, 1), max_move)
            else:
                wanted: Optional[List[ResourceInfo]] = None
                if amount > 0 and res_type:
                    # Continuer la même ressource
                    wanted = gold_res if res_type == "gold" else (meat_res if res_type == "meat" else wood_res)
                else:
                    # Choisir entre or, viande ou bois intelligemment
                    lancer_count = sum(1 for a in all_my_units if a["type"] == "lancer")
                    monk_count = sum(1 for a in all_my_units if a["type"] == "monk")
                    want_monk = (lancer_count >= 2 and monk_count == 0) or (lancer_count >= 5 and monk_count < 2)
                    target_gold = 15 if want_monk else 10
                    if len(my_pawns) < 4:
                        target_gold = 1

                    p_idx = next((i for i, p in enumerate(my_pawns) if p["id"] == u_id), 0)

                    # Répartition stable du flux de récolte (zéro effet pendule) :
                    # pions pairs sur l'or, impairs sur la viande, avec correctifs selon les stocks.
                    if castle["hp"] < castle["max_hp"] - 40 and p_idx == 0 and wood_res:
                        wanted = wood_res                      # 1 pion aide aux réparations
                    elif bank["gold"] >= target_gold + 5 and bank["meat"] < next_meat and meat_res:
                        wanted = meat_res                      # excédent d'or, besoin urgent de viande
                    elif bank["meat"] >= next_meat + 10 and bank["gold"] < target_gold and gold_res:
                        wanted = gold_res                      # excédent de viande, besoin urgent d'or
                    elif p_idx % 2 == 0 and gold_res:
                        wanted = gold_res
                    elif meat_res:
                        wanted = meat_res
                    elif gold_res:
                        wanted = gold_res

                chosen_res = best_source(wanted, pos) if wanted else None
                if chosen_res:
                    r_pos = chosen_res["pos"]
                    dest = go(u, goal_around((r_pos[0], r_pos[1], 1, 1), 1), max_move)

        # --- Comportement des Moines (Monk) ---
        elif u_type == "monk":
            # Allié le plus blessé (position DÉJÀ mise à jour : les combattants ont bougé avant)
            wounded = [a for a in all_my_units if a["id"] != u_id and a.get("hp", 0) < a.get("max_hp", 0)]
            if wounded:
                t = min(wounded, key=lambda a: a["hp"])
                tx, ty = cur_pos[t["id"]]
                dest = go(u, goal_around((tx, ty, 1, 1), reach), max_move)
            else:
                # Pas de blessé : escorter l'armée en restant juste derrière
                if military_units and e_castle:
                    front_unit = min(military_units,
                                     key=lambda m: dist_to_rect(cur_pos[m["id"]], e_castle))
                    fx, fy = cur_pos[front_unit["id"]]
                    dest = go(u, goal_around((fx, fy, 1, 1), 2), max_move)
                else:
                    dest = go(u, staging_goal(), max_move)

        # --- Comportement Militaire (Warrior, Lancer, Archer) ---
        else:
            if macro_state in ("DEFENSE", "DEFENSE_URGENTE"):
                # En défense : intercepter les menaces proches de notre château
                if enemies:
                    if enemy_unit_in_range(pos, reach):
                        dest = pos      # un ennemi est déjà à portée : on reste et on tape
                    else:
                        threats = [e for e in enemies if dist_to_rect((e["x"], e["y"]), castle) <= 12] or enemies
                        # Chaque combattant engage la menace la plus proche de sa propre position
                        target_e = min(threats, key=lambda e: (get_distance_chebyshev(pos, (e["x"], e["y"])),
                                                               e.get("hp", 0)))
                        dest = go(u, goal_around((target_e["x"], target_e["y"], 1, 1), reach), max_move)
                else:
                    dest = go(u, staging_goal(), max_move)

            elif (
                (len(military_units) >= 4) or
                (len(military_units) >= 3 and macro_state == "ASSAUT") or
                (e_castle and e_castle.get("hp", 800) <= 300 and len(military_units) >= 2)
            ):
                # ARMÉE FORMÉE : MARCHE DE GUERRE GROUPÉE !
                if enemy_unit_in_range(pos, reach) or castle_in_range(pos, reach):
                    dest = pos          # déjà au contact : on reste en place pour attaquer
                else:
                    target_goal: Optional[Goal] = None
                    dist_to_ec = dist_to_rect(pos, e_castle) if e_castle else 99

                    # Sous les murs du château adverse (<= 7 cases) ou château vulnérable : siège direct
                    if e_castle and (dist_to_ec <= 7 or e_castle.get("hp", 800) <= 400):
                        target_goal = goal_around(e_castle, reach)
                    else:
                        nearby_e = [e for e in enemies if get_distance_chebyshev(pos, (e["x"], e["y"])) <= 6]
                        if nearby_e:
                            # Éliminer d'abord les ennemis sur notre chemin
                            target_e = sorted(nearby_e, key=lambda e: (0 if e.get("hp", 0) <= 10 else 1,
                                                                        e.get("hp", 0)))[0]
                            target_goal = goal_around((target_e["x"], target_e["y"], 1, 1), reach)
                        elif e_castle:
                            target_goal = goal_around(e_castle, reach)

                    if target_goal is not None:
                        dest = go(u, target_goal, max_move)

            else:  # Moins de 4 combattants : ralliement à l'avant-poste et protection de la base
                nearby_threats = [e for e in enemies if dist_to_rect((e["x"], e["y"]), castle) <= 12]
                if nearby_threats:
                    if enemy_unit_in_range(pos, reach):
                        dest = pos
                    else:
                        target_e = min(nearby_threats, key=lambda e: get_distance_chebyshev(pos, (e["x"], e["y"])))
                        dest = go(u, goal_around((target_e["x"], target_e["y"], 1, 1), reach), max_move)
                elif e_castle:
                    # Ralliement en avant-poste (5 cases devant le château, face à l'ennemi)
                    cx = castle["x"] + castle["width"] // 2
                    cy = castle["y"] + castle["height"] // 2
                    ecx = e_castle["x"] + e_castle["width"] // 2
                    ecy = e_castle["y"] + e_castle["height"] // 2
                    dx = 1 if ecx > cx else (-1 if ecx < cx else 0)
                    dy = 1 if ecy > cy else (-1 if ecy < cy else 0)
                    rally = goal_around((cx + dx * 5, cy + dy * 5, 1, 1), 2)
                    dest = go(u, rally if rally.cells else staging_goal(), max_move)
                else:
                    dest = go(u, staging_goal(), max_move)

        # Mettre à jour l'occupation des cases pour les ordres suivants
        if dest != pos:
            occupied.discard(pos)
            occupied.add(dest)
            cur_pos[u_id] = dest
            _PREV[u_id] = pos
            moves.append(move_order(u_id, dest))

    return moves


# ============================================================================
# 8. Combat : choix des cibles (phase d'action)
# ============================================================================

_TARGET_PRIORITY = {"monk": 0, "archer": 1, "lancer": 2, "warrior": 2, "pawn": 3}


def get_combat_actions(state: State, rules: Rules, team: str, include_pawns: bool = False,
                       busy: Optional[Iterable[int]] = None) -> List[Dict[str, Any]]:
    """Ordres `attack` et `heal` de la phase d'action : TOUTE unité qui peut frapper frappe.

    À appeler avec le `state` du message `action` (positions APRÈS les déplacements du tour).
    Concatène le résultat avec tes ordres `gather` / `deposit` / `recruit` / `repair`.

    Principes (règles §11.2) :
      * les dégâts sont simultanés et une unité tuée frappe quand même : on suit donc les PV
        restants de chaque cible, en tenant compte des attaques déjà décidées ce tour ;
      * 1) on achève d'abord ce qui peut être tué (moines et archers en priorité), 2) sinon on
        concentre le tir sur la cible la plus faible, 3) sinon on tape le château, 4) en dernier
        recours on frappe quand même (un soin adverse peut sauver la cible) ;
      * les unités ayant le moins de choix (une seule cible à portée) sont servies en premier ;
      * un moine soigne l'allié à portée qui a le plus besoin de PV, sans surcharger un même allié.

    Args:
        include_pawns: les pions attaquent aussi. Laisser à False si tes pions récoltent/déposent
                       (une unité n'a qu'une action par tour).
        busy:          ids d'unités à ne pas utiliser (déjà affectées à une autre action).
    """
    units_rules = rules.get("units", {}) if rules else {}
    busy_ids = set(busy or ())
    mine = my_units(state, team)
    enemies = enemy_units(state, team)
    e_castle = enemy_castle(state, team)

    def stat(u: Unit, key: str) -> int:
        return units_rules.get(u["type"], {}).get(key, 0)

    hp_left: Dict[int, int] = {e["id"]: e["hp"] for e in enemies}   # PV restants après dégâts déjà planifiés
    by_id = {e["id"]: e for e in enemies}
    actions: List[Dict[str, Any]] = []

    # ---- attaques
    def reach_of(u: Unit) -> int:
        return stat(u, "range") or 1

    attackers = [u for u in mine
                 if stat(u, "attack") > 0 and u["id"] not in busy_ids
                 and (include_pawns or u["type"] != "pawn")]

    def options(u: Unit) -> List[Unit]:
        p, r = (u["x"], u["y"]), reach_of(u)
        return [e for e in enemies if get_distance_chebyshev(p, (e["x"], e["y"])) <= r]

    opts = {u["id"]: options(u) for u in attackers}
    attackers.sort(key=lambda u: (len(opts[u["id"]]) + (1 if e_castle and dist_to_rect((u["x"], u["y"]), e_castle) <= reach_of(u) else 0),
                                  u["id"]))

    for u in attackers:
        dmg = stat(u, "attack")
        ts = opts[u["id"]]
        c_ok = bool(e_castle) and dist_to_rect((u["x"], u["y"]), e_castle) <= reach_of(u)
        alive = [t for t in ts if hp_left[t["id"]] > 0]
        killable = [t for t in alive if dmg >= hp_left[t["id"]]]

        target_id: Optional[int] = None
        if killable:
            t = min(killable, key=lambda t: (_TARGET_PRIORITY.get(t["type"], 9), hp_left[t["id"]], t["id"]))
            target_id = t["id"]
        elif alive:
            t = min(alive, key=lambda t: (hp_left[t["id"]], _TARGET_PRIORITY.get(t["type"], 9), t["id"]))
            target_id = t["id"]
        elif c_ok:
            target_id = e_castle["id"]            # type: ignore[index]
        elif ts:
            t = max(ts, key=lambda t: (hp_left[t["id"]], -t["id"]))
            target_id = t["id"]

        if target_id is None:
            continue
        if not (e_castle and target_id == e_castle["id"]):
            hp_left[target_id] -= dmg
        actions.append({"type": "attack", "unit": u["id"], "target": target_id})

    # ---- soins
    healed: Dict[int, int] = {}
    for m in mine:
        heal = stat(m, "heal")
        if heal <= 0 or m["id"] in busy_ids:
            continue
        r = reach_of(m)
        mp = (m["x"], m["y"])
        needy = [a for a in mine
                 if get_distance_chebyshev(mp, (a["x"], a["y"])) <= r
                 and a["hp"] + healed.get(a["id"], 0) < a["max_hp"]]
        if not needy:
            continue
        t = min(needy, key=lambda a: ((a["hp"] + healed.get(a["id"], 0)) / a["max_hp"], a["id"]))
        healed[t["id"]] = healed.get(t["id"], 0) + heal
        actions.append({"type": "heal", "unit": m["id"], "target": t["id"]})

    return actions


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

    # --- Goal : les cases déjà prises ne sont plus visées ---
    g = Goal(state, [(30, 30), (31, 30)])
    assert set(g.field_for({(30, 30)})) >= {(31, 30)} and g.field_for({(30, 30)})[(31, 30)] == 0
    assert g.field_for({(30, 30)}).get((30, 30), INF) > 0          # case prise : plus un but
    assert g.field_for({(30, 30), (31, 30)})[(30, 30)] == 0         # tout pris : repli sur toutes les cases

    # --- Combat : tout le monde tape, tir concentré, pas de gaspillage ---
    rules_t = {"units": {"warrior": {"attack": 8, "range": 1}, "archer": {"attack": 9, "range": 4},
                         "monk": {"heal": 10, "range": 2}}}
    def U(i, team, t, x, y, hp, mx):
        return {"id": i, "team": team, "type": t, "x": x, "y": y, "hp": hp, "max_hp": mx}
    st = {"width": 80, "height": 74, "grid": grid, "resources": [],
          "buildings": state["buildings"],
          "units": [U(10, "purple", "warrior", 40, 40, 60, 60), U(11, "purple", "warrior", 40, 41, 60, 60),
                    U(12, "purple", "archer", 38, 40, 35, 35), U(13, "purple", "monk", 39, 40, 20, 40),
                    U(20, "yellow", "pawn", 41, 40, 5, 30), U(21, "yellow", "warrior", 41, 41, 60, 60)]}
    acts = get_combat_actions(st, rules_t, "purple")
    atk = {a["unit"]: a["target"] for a in acts if a["type"] == "attack"}
    assert set(atk) == {10, 11, 12}, atk                      # les 3 unités à portée attaquent
    assert sorted(atk.values()).count(20) == 1, atk            # le pion (5 PV) est achevé UNE seule fois
    assert any(a["type"] == "heal" and a["target"] == 13 for a in acts), acts   # le moine se soigne
    print("combat :", acts)
    print("OK")
