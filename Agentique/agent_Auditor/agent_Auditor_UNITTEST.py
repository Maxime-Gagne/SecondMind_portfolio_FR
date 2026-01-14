#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Unitaire: Agent Auditor
Cible : agentique/sous_agents_gouvernes/agent_Auditor/agent_Auditor.py
Objectif : Valider l'analyse statique (AST), la sécurité et la conformité des contrats.
"""

import unittest
import ast
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path
from types import SimpleNamespace

# Import de la classe à tester (et des visiteurs internes si besoin d'accès direct)
try:
    from agentique.sous_agents_gouvernes.agent_Auditor.agent_Auditor import (
        AgentAuditor,
        ContractComplianceVisitor,
        FunctionHygieneVisitor,
        ShadowComplianceVisitor,
        TrackedDataclass,
    )
except ImportError:
    # Fallback pour exécution hors contexte (les tests skipperont si imports manquants)
    AgentAuditor = None


class TestAgentAuditor(unittest.TestCase):
    def setUp(self):
        """Configuration d'un auditeur 'coquille vide' pour les tests."""
        if AgentAuditor is None:
            self.skipTest("AgentAuditor non importable")

        # On contourne le __init__ lourd (chargement YAML, Logger)
        self.auditor = AgentAuditor.__new__(AgentAuditor)

        # Injection des dépendances mockées
        self.auditor.logger = MagicMock()
        self.auditor.auditor = MagicMock()  # L'auditor_base interne

        # Config minimale pour les tests
        self.auditor.config = {
            "securite": {
                "sanctuaires": ["/memoire/persistante"],
                "patterns_interdits": [
                    {
                        "pattern": "rmtree",
                        "message": "Suppression interdite",
                        "gravite": "CRITIQUE",
                    }
                ],
            },
            "vocabulaire": {"exceptions_autorisees": []},
            "perimetre": {"exclusions_globales": []},
        }
        # Application de la config
        self.auditor.sanctuaires = ["/memoire/persistante"]
        self.auditor.patterns_interdits = [
            {"pattern": "rmtree", "message": "Suppression", "gravite": "CRITIQUE"}
        ]
        self.auditor.seuil_alerte = "CRITIQUE"

    # =========================================================================
    # 1. TEST AST : CONFORMITÉ CONTRATS (ContractComplianceVisitor)
    # =========================================================================

    def test_ast_contrats_manquants(self):
        """Vérifie la détection d'arguments obligatoires manquants."""
        # Définition : 'MyClass' requiert 'a' et 'b'
        defs = {"MyClass": {"all": {"a", "b", "c"}, "required": {"a", "b"}}}

        # Code à tester : 'MyClass(a=1)' -> Manque 'b'
        code = "x = MyClass(a=1)"
        tree = ast.parse(code)

        visitor = ContractComplianceVisitor(defs)
        visitor.visit(tree)

        self.assertEqual(len(visitor.violations), 1)
        self.assertIn("Champ OBLIGATOIRE manquant", visitor.violations[0])
        self.assertIn("'b'", visitor.violations[0])

    def test_ast_contrats_inconnus(self):
        """Vérifie la détection d'arguments inconnus (typos)."""
        defs = {"MyClass": {"all": {"a"}, "required": {"a"}}}

        # Code à tester : 'MyClass(a=1, z=2)' -> 'z' est inconnu
        code = "x = MyClass(a=1, z=2)"
        tree = ast.parse(code)

        visitor = ContractComplianceVisitor(defs)
        visitor.visit(tree)

        self.assertEqual(len(visitor.violations), 1)
        self.assertIn("Champ INCONNU 'z'", visitor.violations[0])

    # =========================================================================
    # 2. TEST AST : HYGIÈNE (FunctionHygieneVisitor)
    # =========================================================================

    def test_ast_variables_mortes(self):
        """Vérifie la détection de variables assignées mais jamais lues."""
        code = """
def ma_fonction():
    vivante = 1
    morte = 2  # Jamais lue
    print(vivante)
"""
        tree = ast.parse(code)
        visitor = FunctionHygieneVisitor()
        visitor.visit(tree)

        self.assertEqual(len(visitor.violations), 1)
        self.assertIn("Variables mortes", visitor.violations[0])
        self.assertIn("'morte'", visitor.violations[0])

    # =========================================================================
    # 3. TEST AST : SHADOW OBJECTS (ShadowComplianceVisitor)
    # =========================================================================

    def test_ast_shadow_objects(self):
        """Vérifie la détection de dictionnaires imitant des dataclasses."""
        # Contrat : 'Prompt' a les champs 'text', 'author'
        defs = {"Prompt": {"text", "author"}}

        # Code : Un dict qui a exactement ces clés
        code = "fake_obj = {'text': 'Salut', 'author': 'Moi'}"
        tree = ast.parse(code)

        visitor = ShadowComplianceVisitor(defs)
        visitor.visit(tree)

        self.assertEqual(len(visitor.violations), 1)
        self.assertIn("imite le contrat 'Prompt'", visitor.violations[0])

    # =========================================================================
    # 4. TEST SÉCURITÉ (auditer_securite_fichier)
    # =========================================================================

    def test_securite_detection_rmtree(self):
        """Vérifie que rmtree sur un sanctuaire déclenche une alerte."""
        # Simulation lecture fichier
        contenu_dangereux = """
import shutil
shutil.rmtree('/memoire/persistante/fichiers')
"""
        mock_path = MagicMock(spec=Path)
        mock_path.name = "danger.py"
        mock_path.read_text.return_value = contenu_dangereux

        # Act
        alertes = self.auditor.auditer_securite_fichier(mock_path)

        # Assert
        self.assertTrue(any("Code destructif" in a for a in alertes))
        self.assertTrue(any("sanctuaire '/memoire/persistante'" in a for a in alertes))

    def test_securite_exception_rotation(self):
        """Vérifie que la présence de mots-clés 'backup' autorise la suppression."""
        contenu_legitime = """
# Rotation des logs
shutil.copy(f, f + ".backup")
shutil.rmtree('/memoire/persistante/logs_old') # Suppression légitime après backup
"""
        mock_path = MagicMock(spec=Path)
        mock_path.name = "rotation.py"
        mock_path.read_text.return_value = contenu_legitime

        alertes = self.auditor.auditer_securite_fichier(mock_path)

        # Ne doit pas lever d'alerte critique grâce à "backup"
        critiques = [a for a in alertes if "Code destructif" in a]
        self.assertEqual(len(critiques), 0)

    # =========================================================================
    # 5. TEST RUNTIME : TRACKED DATACLASS
    # =========================================================================

    def test_tracked_dataclass_usage(self):
        """Vérifie que le wrapper TrackedDataclass détecte les champs non lus."""

        @unittest.dataclass
        class MockData:
            lu: str
            ignore: str

        data = MockData(lu="ok", ignore="pas lu")
        tracked = TrackedDataclass(data)

        # Simulation : L'agent lit 'lu' mais pas 'ignore'
        _ = tracked.lu

        unused = tracked.get_unused_fields()
        self.assertIn("ignore", unused)
        self.assertNotIn("lu", unused)

    def test_valider_utilisation_complete(self):
        """Test de la méthode haut niveau de l'agent."""
        # On mock un objet avec get_unused_fields
        mock_obj = MagicMock()
        mock_obj.get_unused_fields.return_value = {"champ_oublie"}
        mock_obj.get_class_name.return_value = "TestClass"

        # On vérifie que ça retourne False (invalide) et loggue un warning
        res = self.auditor.valider_utilisation_complete_dataclass(mock_obj)

        self.assertFalse(res)
        self.auditor.logger.log_warning.assert_called()

    # =========================================================================
    # 6. TEST ENCODAGE (auditer_encodage_fichiers)
    # =========================================================================

    def test_audit_encodage_detecte_problemes(self):
        """Vérifie la détection de newline manquante."""
        # Mock d'un fichier sans newline
        mock_file = MagicMock(spec=Path)
        mock_file.is_file.return_value = True
        mock_file.suffix = ".py"
        mock_file.stat.return_value = SimpleNamespace(st_mtime=123, st_size=10)

        # Simulation : auditor_base renvoie un chemin valide
        self.auditor.auditor.get_path.return_value = "/fake/dir"

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.rglob", return_value=[mock_file]),
            patch("builtins.open", mock_open(read_data="pas de retour ligne")),
            patch.object(self.auditor, "_load_encoding_registry", return_value={}),
            patch.object(self.auditor, "_save_encoding_registry"),
        ):
            # On force la vérification complète
            res = self.auditor.auditer_encodage_fichiers(
                dossiers_a_verifier=["test"], check_standards=True
            )

            self.assertEqual(len(res["violations"]), 1)
            self.assertEqual(res["violations"][0]["type"], "NEWLINE_MANQUANTE")


if __name__ == "__main__":
    unittest.main()
