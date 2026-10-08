import unittest
from economy import get_virtual_bank, get_castle_action, sort_actions_for_server

class TestEconomy(unittest.TestCase):

    def test_get_virtual_bank(self):
        # On simule l'état de nos unités (le Tacticien/Serveur nous donne ça)
        team_units = {
            1: {"inventory": {"gold": 2, "meat": 3, "wood": 0}}, # Unité 1 a des ressources
            2: {"inventory": {"gold": 0, "meat": 0, "wood": 1}}, # Unité 2 a du bois
        }
        
        # Actions décidées par le Tacticien pour ce tour
        planned_actions = [
            {"type": "move", "unit_id": 2},     # Unité 2 se déplace, pas de dépot
            {"type": "deposit", "unit_id": 1}   # Unité 1 dépose son inventaire !
        ]
        
        # Stocks actuels : 10 or, 10 viande, 10 bois
        v_gold, v_meat, v_wood = get_virtual_bank(10, 10, 10, planned_actions, team_units)
        
        # Vérifications
        self.assertEqual(v_gold, 12, "L'or de l'unité 1 doit être ajouté (10 + 2)")
        self.assertEqual(v_meat, 13, "La viande de l'unité 1 doit être ajoutée (10 + 3)")
        self.assertEqual(v_wood, 10, "Le bois de l'unité 2 n'est pas ajouté car elle n'a pas fait deposit")

    def test_get_castle_action_repair(self):
        # Cas 1 : On a 5 bois, le château a perdu 10 PV (100 - 90) -> On doit réparer
        action = get_castle_action(gold=10, meat=10, wood=5, castle_hp=90, castle_max_hp=100, next_meat_cost=5, target_unit="Pawn")
        self.assertEqual(action, {"type": "repair"}, "On doit réparer si on a du bois et que ça ne gaspille rien")
        
        # Cas 2 : Zéro Gaspillage. On a 5 bois mais il ne manque qu'1 PV (100 - 99) -> On ne répare PAS
        action = get_castle_action(gold=10, meat=10, wood=5, castle_hp=99, castle_max_hp=100, next_meat_cost=5, target_unit=None)
        self.assertIsNone(action, "La règle zéro gaspillage doit empêcher la réparation")

    def test_get_castle_action_recruit(self):
        # Cas 1 : On demande un Archer (10 or). On a 10 or et 15 viande (coût prochain = 12) -> Succès
        action = get_castle_action(gold=10, meat=15, wood=0, castle_hp=100, castle_max_hp=100, next_meat_cost=12, target_unit="Archer")
        self.assertEqual(action, {"type": "recruit", "unit": "Archer"}, "Le recrutement de l'archer devrait être validé")

        # Cas 2 : On demande un Archer mais pas assez d'or (9 au lieu de 10) -> Épargne stricte (None)
        action = get_castle_action(gold=9, meat=15, wood=0, castle_hp=100, castle_max_hp=100, next_meat_cost=12, target_unit="Archer")
        self.assertIsNone(action, "Épargne stricte si pas assez d'or")

        # Cas 3 : On demande un Archer mais pas assez de viande (11 au lieu de 12) -> Épargne stricte (None)
        action = get_castle_action(gold=10, meat=11, wood=0, castle_hp=100, castle_max_hp=100, next_meat_cost=12, target_unit="Archer")
        self.assertIsNone(action, "Épargne stricte si pas assez de viande")

    def test_sort_actions(self):
        # Liste d'actions en désordre
        actions = [
            {"type": "attack", "target": "enemy"},
            {"type": "recruit", "unit": "Pawn"},
            {"type": "deposit", "unit_id": 1},
            {"type": "move", "dir": "N"},
            {"type": "repair"}
        ]
        
        sorted_acts = sort_actions_for_server(actions)
        
        # L'ordre doit être : deposit d'abord (priorité 0)
        self.assertEqual(sorted_acts[0]["type"], "deposit")
        
        # Ensuite recruit/repair (priorité 1). Python garde l'ordre relatif (recruit était avant repair)
        self.assertEqual(sorted_acts[1]["type"], "recruit")
        self.assertEqual(sorted_acts[2]["type"], "repair")
        
        # Ensuite les autres (priorité 2). attack était avant move.
        self.assertEqual(sorted_acts[3]["type"], "attack")
        self.assertEqual(sorted_acts[4]["type"], "move")

if __name__ == '__main__':
    unittest.main()
