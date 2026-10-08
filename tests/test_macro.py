"""Verification : python -m unittest discover -s tests -v."""

import unittest
from copy import deepcopy
from math import inf
from unittest.mock import patch

import macro


RULES = {
    "units": {
        "pawn": {"attack": 3, "range": 1},
        "warrior": {"attack": 8, "range": 1},
        "lancer": {"attack": 10, "range": 2},
        "archer": {"attack": 9, "range": 4},
        "monk": {"attack": 0, "range": 2},
    },
}


def unit(uid, team, kind, x, y, hp=30):
    return {"id": uid, "team": team, "type": kind,
            "x": x, "y": y, "hp": hp, "max_hp": 60, "carrying": None}


def initial_state():
    return {
        "turn": 1,
        "teams": {
            "purple": {"resources": {"gold": 20, "meat": 0, "wood": 12},
                       "recruited": 4, "next_meat_cost": 5},
            "yellow": {"resources": {"gold": 0, "meat": 0, "wood": 0},
                       "recruited": 0, "next_meat_cost": 1},
        },
        "buildings": [
            {"id": 1, "team": "purple", "type": "castle", "x": 10, "y": 10,
             "width": 4, "height": 2, "hp": 800, "max_hp": 800},
            {"id": 2, "team": "yellow", "type": "castle", "x": 40, "y": 40,
             "width": 4, "height": 2, "hp": 800, "max_hp": 800},
        ],
        "units": [unit(i, "purple", "pawn", 9, 9 + i) for i in range(3, 6)]
                 + [unit(6, "yellow", "warrior", 35, 35)],
    }


class MacroTests(unittest.TestCase):
    def setUp(self):
        self.state = initial_state()
        self.rules = deepcopy(RULES)

    def metrics(self, **kwargs):
        return macro.extract_metrics(self.state, self.rules, "purple", **kwargs)

    def strategy(self, **kwargs):
        return macro.analyze_state(self.state, self.rules, "purple", **kwargs)

    def test_real_protocol_and_rules_stats(self):
        self.rules["units"]["pawn"]["attack"] = 7
        m = self.metrics()
        self.assertEqual((m.gold, m.meat, m.wood, m.next_meat_cost), (20, 0, 12, 5))
        self.assertEqual((m.castle_hp, m.castle_max_hp, m.pawn_count), (800, 800, 3))
        self.assertEqual(m.own_damage, 21)
        self.assertEqual(m.military_ratio, 21 / 8)

    def test_castle_distance_all_sides(self):
        castle = self.state["buildings"][0]
        for x, y, expected in [(9, 10, 1), (14, 11, 1), (11, 9, 1),
                               (12, 12, 1), (14, 12, 1), (17, 11, 4),
                               (6, 6, 4), (10, 10, 0)]:
            with self.subTest(x=x, y=y):
                self.assertEqual(macro.get_castle_distance({"x": x, "y": y}, castle),
                                 expected)

    def test_archer_in_range_of_right_edge_is_urgent(self):
        self.state["units"].append(unit(7, "yellow", "archer", 17, 11))
        m = self.metrics()
        self.assertEqual(m.nearest_attacker_distance, 4)
        self.assertEqual(m.immediate_enemy_damage, 9)
        self.assertEqual(self.strategy(), "DEFENSE_URGENTE")
        self.assertEqual(macro.get_multipliers(self.strategy())["attack"], 5)

    def test_monks_and_dead_units_do_not_create_threat(self):
        self.state["units"] = [unit(9, "yellow", "monk", 14, 11),
                               unit(10, "yellow", "warrior", 14, 11, hp=0)]
        m = self.metrics()
        self.assertEqual(m.nearest_enemy_distance, 1)
        self.assertEqual(m.nearest_attacker_distance, inf)
        self.assertEqual(m.military_ratio, 1)
        self.assertFalse(m.threatened)
        self.assertEqual(self.strategy(), "ECO_FOCUS")

    def test_empty_armies_have_neutral_ratio(self):
        self.state["units"] = []
        self.assertEqual(self.metrics().military_ratio, 1)
        self.assertEqual(self.metrics().nearest_enemy_distance, inf)

    def test_defense_with_enough_local_defenders(self):
        self.state["units"].append(unit(7, "yellow", "warrior", 19, 11))
        self.assertEqual(self.strategy(), "DEFENSE")
        self.state["buildings"][0]["hp"] = 200
        self.assertEqual(self.strategy(), "DEFENSE_URGENTE")

    def test_local_weakness_overrides_global_superiority(self):
        self.state["units"] = [unit(i, "purple", "lancer", 30, 30)
                               for i in range(10, 20)]
        self.state["units"].append(unit(20, "yellow", "warrior", 19, 11))
        self.assertGreater(self.metrics().military_ratio, 10)
        self.assertEqual(self.strategy(), "DEFENSE_URGENTE")

    def test_defense_exit_margin(self):
        self.state["teams"]["purple"]["resources"]["meat"] = 10
        self.state["units"][-1].update(x=21, y=11)  # Distance 8.
        self.assertEqual(self.strategy(), "EQUILIBRE")
        self.assertEqual(self.strategy(previous_state="DEFENSE"), "DEFENSE")
        self.state["units"][-1]["x"] = 23  # Distance 10 : sortie de defense.
        self.assertEqual(self.strategy(previous_state="DEFENSE"), "EQUILIBRE")

    def test_assault_hysteresis_and_worker_guard(self):
        self.state["units"] += [unit(7, "purple", "warrior", 20, 20),
                                unit(8, "purple", "warrior", 20, 21)]
        self.state["units"][-3]["type"] = "lancer"
        self.rules["units"]["lancer"]["attack"] = 18  # Ratio 25/18.
        self.state["teams"]["purple"]["resources"]["meat"] = 10
        self.assertEqual(self.strategy(), "EQUILIBRE")
        self.assertEqual(self.strategy(previous_state="ASSAUT"), "ASSAUT")
        self.state["units"][-3]["type"] = "warrior"  # Ratio 25/8.
        self.assertEqual(self.strategy(), "ASSAUT")
        self.state["units"] = self.state["units"][:3]
        self.assertEqual(self.strategy(), "EQUILIBRE")  # Pions seuls.

    def test_missing_workers_or_meat_favors_economy(self):
        self.assertEqual(self.strategy(), "ECO_FOCUS")
        self.state["teams"]["purple"]["resources"]["meat"] = 5
        self.assertEqual(self.strategy(), "EQUILIBRE")
        self.state["units"].pop(0)
        self.assertEqual(self.strategy(), "ECO_FOCUS")

    def test_weights_alias_and_independent_copies(self):
        weights = macro.get_multipliers("DEFENSE_URGENTE")
        self.assertTrue(all(key in weights for key in
                            ("gather_gold", "gather_meat", "gather_wood", "heal")))
        weights["attack"] = -1
        self.assertEqual(macro.get_multipliers("DEFENSE_URGENTE")["attack"], 5)
        self.assertEqual(macro.get_multipliers("DEVELOPPEMENT"),
                         macro.get_multipliers("ECO_FOCUS"))

    def test_detailed_api_and_team_symmetry_do_not_mutate_inputs(self):
        snapshot = deepcopy(self.state)
        result = macro.analyze_macro(self.state, self.rules, "purple")
        self.assertEqual(result["state"], self.strategy())
        self.assertEqual(result["weights"], macro.get_multipliers(result["state"]))
        yellow = macro.extract_metrics(self.state, self.rules, "yellow")
        self.assertEqual(yellow.own_damage, 8)
        self.assertEqual(yellow.enemy_damage, 9)
        self.assertEqual(self.state, snapshot)

    def test_bot_remembers_strategy_and_passes_weights(self):
        import bot
        old_state = bot.previous_macro_state
        try:
            bot.previous_macro_state = "DEFENSE"
            self.state["units"][-1].update(x=21, y=11)
            with patch.object(bot.micro, "generate_and_score_actions", return_value=[]) as micro_call, \
                 patch.object(bot.economy, "get_economy_actions", return_value=[]) as eco_call:
                self.assertEqual(bot.compute_turn_actions(self.state, self.rules, "purple"), [])
                self.assertEqual(bot.previous_macro_state, "DEFENSE")
                self.assertEqual(micro_call.call_args.args[3]["attack"], 2.5)
                self.assertEqual(eco_call.call_args.args[3], "DEFENSE")
        finally:
            bot.previous_macro_state = old_state


if __name__ == "__main__":
    unittest.main()
