#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Unitaire: Agent Code
Cible : agentique/sous_agents_gouvernes/agent_Code/agent_Code.py
Objectif : Valider la recherche hybride (Vecteur/Graphe), la génération de squelette et l'intégration Doc externe.
"""

import unittest
import json
from unittest.mock import MagicMock, patch, mock_open, ANY
from pathlib import Path
from types import SimpleNamespace

# Imports des contrats
from agentique.base.contrats_interface import ContexteCode, Souvenir

# Import conditionnel de l'agent
try:
    from agentique.sous_agents_gouvernes.agent_Code.agent_Code import AgentCode
except ImportError:
    AgentCode = None


class TestAgentCode(unittest.TestCase):
    def setUp(self):
        if AgentCode is None:
            self.skipTest("AgentCode non importable")

        # 1. Instanciation "Coquille Vide" (Bypass __init__ lourd)
        self.agent = AgentCode.__new__(AgentCode)

        # 2. Injection Mocks Dépendances
        self.agent.logger = MagicMock()
        self.agent.auditor = MagicMock()
        self.agent.moteur_vecteur = MagicMock()
        self.agent.extractor_manager = MagicMock()

        # 3. Injection Données en Mémoire (Simulation Index chargé)
        # Architecture Mockée (Graphe)
        self.agent.arch = {
            "files": {
                "main.py": {
                    "path": "src/main.py",
                    "docstring": "Point entrée",
                    "classes": {"App": {"methods": ["run"]}},
                    "functions": [],
                    "outgoing_edges": ["utils.py"],  # Dépendance
                },
                "utils.py": {
                    "path": "src/utils.py",
                    "docstring": "Utilitaires",
                    "classes": {},
                    "functions": ["helper"],
                    "outgoing_edges": [],
                },
            }
        }

        # Mocks FAISS & Embedder
        self.agent.index = MagicMock()
        self.agent.embedder = MagicMock()
        self.agent.meta = {"chunks": [{"id": "chunk_1"}, {"id": "chunk_2"}]}
        self.agent.chunk_offsets = {"chunk_1": 0, "chunk_2": 100}

        # Config Mock
        self.agent.config = {"output_paths": {}}
        self.agent.chunks_jsonl = Path("/fake/chunks.jsonl")

    # =========================================================================
    # 1. TEST RECHERCHE HYBRIDE (Chercher Code)
    # =========================================================================

    def test_chercher_code_logique_expansion(self):
        """
        Vérifie que la recherche combine:
        1. Vecteur (Simulé)
        2. Mots-clés (Symbolique)
        3. Graphe (Expansion dépendances)
        """
        # A. Mock Vecteur : Retourne un chunk venant de 'main.py'
        mock_chunk = MagicMock()
        mock_chunk.module = "main.py"
        self.agent._search_vector = MagicMock(return_value=[mock_chunk])

        # B. Mock Symbolique : Retourne rien pour l'instant
        self.agent._trouver_modules_par_mots_cles = MagicMock(return_value=[])

        # C. Exécution
        res = self.agent.chercher_code("question", top_k=5)

        # D. Assertions
        modules = res["modules_concernes"]

        # 'main.py' trouvé via vecteur
        self.assertIn("main.py", modules)
        # 'utils.py' doit être présent via expansion de graphe (main -> utils)
        self.assertIn("utils.py", modules)

    def test_trouver_modules_par_mots_cles(self):
        """Vérifie la recherche symbolique simple dans l'architecture."""
        # Query contient "utils" -> doit matcher "utils.py"
        res = self.agent._trouver_modules_par_mots_cles(
            "je veux voir utils s'il te plait"
        )

        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["nom"], "utils.py")

    # =========================================================================
    # 2. TEST SQUELETTE DYNAMIQUE
    # =========================================================================

    def test_generer_squelette_partiel(self):
        """Vérifie que le squelette texte est généré correctement pour les modules ciblés."""
        # On demande le squelette pour 'main.py' uniquement
        res = self.agent._generer_squelette_partiel(["main.py"])

        self.assertIn("MODULE : main.py", res)
        self.assertIn("class App", res)
        self.assertIn("def run", res)

        # 'utils.py' ne doit pas y être (filtrage)
        self.assertNotIn("utils.py", res)
        self.assertNotIn("def helper", res)

    # =========================================================================
    # 3. TEST HYDRATATION OBJETS (Lecture JSONL)
    # =========================================================================

    def test_search_vector_hydration(self):
        """Vérifie que la recherche FAISS lit bien le fichier JSONL pour créer des ContexteCode."""
        # Setup FAISS Mock
        # search retourne scores=[[0.9]], indices=[[0]] (correspond à chunk_1)
        self.agent.embedder.encode.return_value = [[0.1, 0.2]]
        self.agent.index.search.return_value = ([[0.9]], [[0]])

        # Setup File Mock (Simulation lecture JSONL à l'offset)
        fake_json_line = json.dumps(
            {
                "id": "chunk_1",
                "type": "snippet",
                "module": "test.py",
                "contenu": "print('test')",
            }
        ).encode("utf-8")

        mock_file = MagicMock()
        # --- CORRECTION CRUCIALE ICI ---
        # On force le context manager à retourner NOTRE mock configuré
        mock_file.__enter__.return_value = mock_file
        mock_file.readline.return_value = fake_json_line

        # Patch open pour intercepter la lecture de chunks_jsonl
        with patch("builtins.open", return_value=mock_file):
            results = self.agent._search_vector("query")

            # Vérifications
            self.assertEqual(len(results), 1)
            obj = results[0]
            self.assertIsInstance(obj, ContexteCode)
            self.assertEqual(obj.id, "chunk_1")
            self.assertEqual(obj.contenu, "print('test')")
            # Vérifie que seek a été appelé avec l'offset de chunk_1 (0)
            mock_file.seek.assert_called_with(0)

    # =========================================================================
    # 4. TEST DOC EXTERNE & ROBUSTESSE
    # =========================================================================

    @patch("requests.post")
    def test_consulter_documentation_externe_succes(self, mock_post):
        """Vérifie le formatage si l'API répond 200."""
        # Mock réponse API
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "results": [
                {"package": "Pydantic", "content": "BaseModel info", "score": 0.9}
            ]
        }

        res = self.agent.consulter_documentation_externe("pydantic")

        self.assertIn("DOCUMENTATION OFFICIELLE", res)
        self.assertIn("Pydantic", res)
        self.assertIn("BaseModel info", res)

    @patch("requests.post")
    def test_consulter_documentation_externe_timeout(self, mock_post):
        """Vérifie que l'agent ne crashe pas si le serveur doc est down."""
        import requests

        mock_post.side_effect = requests.exceptions.ConnectionError("Down")

        res = self.agent.consulter_documentation_externe("query")

        self.assertEqual(res, "")  # Doit retourner vide, pas d'erreur
        self.agent.logger.log_warning.assert_called()  # Doit logger le warning

    # =========================================================================
    # 5. TEST INTÉGRATION FOURNIR_CONTEXTE
    # =========================================================================

    def test_fournir_contexte_declenchement_doc(self):
        """Vérifie que 'pydantic' dans la query déclenche la recherche doc externe."""
        # Mocks internes
        self.agent.chercher_code = MagicMock(
            return_value={
                "modules_concernes": [],
                "contexte_objets": [
                    ContexteCode(id="1", type="snip", module="m", name="n")
                ],
            }
        )
        self.agent._generer_squelette_partiel = MagicMock(return_value="")

        # Mock Doc Externe
        self.agent.consulter_documentation_externe = MagicMock(
            return_value="DOC PYDANTIC"
        )

        # Action : Query contenant un mot clé critique "pydantic"
        res = self.agent.fournir_contexte("comment utiliser pydantic validator")

        # Assertions
        # Doit contenir le code (ContexteCode) ET la doc (Souvenir)
        types = [type(x).__name__ for x in res]
        self.assertIn("ContexteCode", types)
        self.assertIn("Souvenir", types)

        # Vérif appel
        self.agent.consulter_documentation_externe.assert_called()


if __name__ == "__main__":
    unittest.main()
