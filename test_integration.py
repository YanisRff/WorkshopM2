import unittest
import bot

class TestIntegration(unittest.TestCase):
    def setUp(self):
        W, H = 80, 74
        grid = [[1 for _ in range(W)] for _ in range(H)]
        # Put castle at (27, 27)
        for dy in range(2):
            for dx in range(4):
                grid[27 + dy][27 + dx] = 6
                grid[45 + dy][49 + dx] = 7

        self.rules = {
            "legend": ["water", "ground", "rock", "gold", "tree", "sheep", "castle_purple", "castle_yellow"],
            "walkable": ["ground", "tree", "sheep"],
            "units": {
                "pawn": {"hp": 30, "move": 4, "attack": 3, "heal": 0, "range": 1, "cost": {"gold": 1}},
                "warrior": {"hp": 60, "move": 3, "attack": 8, "heal": 0, "range": 1, "cost": {"gold": 5}},
                "lancer": {"hp": 90, "move": 2, "attack": 10, "heal": 0, "range": 2, "cost": {"gold": 10}},
                "archer": {"hp": 35, "move": 1, "attack": 9, "heal": 0, "range": 4, "cost": {"gold": 10}},
                "monk": {"hp": 40, "move": 1, "attack": 0, "heal": 10, "range": 2, "cost": {"gold": 15}}
            },
            "buildings": {
                "castle": {"width": 4, "height": 2, "hp": 800}
            }
        }

        self.state = {
            "turn": 1,
            "width": W,
            "height": H,
            "grid": grid,
            "teams": {
                "purple": {
                    "name": "AntiGravityBot",
                    "resources": {"gold": 15, "wood": 20, "meat": 10},
                    "unit_count": 3,
                    "recruited": 0,
                    "next_meat_cost": 1
                },
                "yellow": {
                    "name": "Robot",
                    "resources": {"gold": 0, "wood": 0, "meat": 0},
                    "unit_count": 3,
                    "recruited": 0,
                    "next_meat_cost": 1
                }
            },
            "buildings": [
                {"id": 1, "team": "purple", "type": "castle", "x": 27, "y": 27, "width": 4, "height": 2, "hp": 780, "max_hp": 800},
                {"id": 2, "team": "yellow", "type": "castle", "x": 49, "y": 45, "width": 4, "height": 2, "hp": 800, "max_hp": 800}
            ],
            "resources": [
                {"x": 25, "y": 27, "resource": "gold"},
                {"x": 35, "y": 27, "resource": "meat"},
                {"x": 27, "y": 32, "resource": "wood"}
            ],
            "units": [
                {"id": 3, "team": "purple", "type": "pawn", "x": 26, "y": 27, "hp": 30, "max_hp": 30, "carrying": {"resource": "gold", "amount": 5}},
                {"id": 4, "team": "purple", "type": "pawn", "x": 26, "y": 28, "hp": 30, "max_hp": 30, "carrying": None},
                {"id": 5, "team": "purple", "type": "warrior", "x": 30, "y": 30, "hp": 60, "max_hp": 60, "carrying": None},
                {"id": 6, "team": "yellow", "type": "pawn", "x": 31, "y": 30, "hp": 30, "max_hp": 30, "carrying": None}
            ]
        }

    def test_moves_phase(self):
        moves = bot.compute_turn_moves(self.state, self.rules, "purple")
        self.assertIsInstance(moves, list)
        for m in moves:
            self.assertIn("unit", m)
            self.assertIn("to", m)
            self.assertEqual(len(m["to"]), 2)

    def test_actions_phase(self):
        actions = bot.compute_turn_actions(self.state, self.rules, "purple")
        self.assertIsInstance(actions, list)
        self.assertTrue(len(actions) > 0)

        # Check ordering: deposit must be before recruit/repair, which must be before attack
        types = [a["type"] for a in actions]
        print(f"Generated actions: {types}")

        # If deposit exists, it must be first
        if "deposit" in types:
            deposit_idx = types.index("deposit")
            if "recruit" in types:
                self.assertLess(deposit_idx, types.index("recruit"))
            if "attack" in types:
                self.assertLess(deposit_idx, types.index("attack"))

if __name__ == "__main__":
    unittest.main()
