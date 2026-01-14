#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Unitaire: Recherche Memoire Tool
Cible : agentique/sous_agents_gouvernes/agent_Recherche/recherche_memoire.py
Objectif : Valider le routing des recherches, la lecture physique des fichiers et la cartographie.
"""

import unittest
from unittest.mock import MagicMock, patch, mock_open
import json

# Import du module à tester
from agentique.sous_agents_gouvernes.agent_Recherche.recherche_memoire import (
    RechercheMemoireTool,
)
from agentique.base.contrats_interface import Souvenir, ResultatRecherche


class TestRechercheMemoireTool(unittest.TestCase):
    def setUp(self):
        """Configuration des mocks."""
        # On mock l'AgentRecherche injecté
        self.mock_agent_recherche = MagicMock()
        self.tool = RechercheMemoireTool(self.mock_agent_recherche)

    # =========================================================================
    # 1. TEST DU DISPATCHER (executer)
    # =========================================================================

    def test_executer_routing_code(self):
        """Vérifie le routing 'code' vers recherche_fichier_hors_memoire."""
        # Arrange : On simule un retour positif de l'agent recherche
        mock_res = ResultatRecherche(
            souvenirs_bruts=[Souvenir("Contenu", "Titre.py", "py", 1.0)],
            nb_fichiers_scannes=1,
        )
        self.mock_agent_recherche.recherche_fichier_hors_memoire.return_value = mock_res

        # Act
        res = self.tool.executer("code", "test.py")

        # Assert
        self.mock_agent_recherche.recherche_fichier_hors_memoire.assert_called_with(
            "test.py"
        )
        self.assertTrue(res["succes"])
        self.assertEqual(res["nb_resultats"], 1)

    def test_executer_routing_verbatim(self):
        """Vérifie le routing 'verbatim' vers recherche_interaction_verbatim."""
        self.mock_agent_recherche.recherche_interaction_verbatim.return_value = (
            ResultatRecherche([], 0)
        )
        self.tool.executer("verbatim", "phrase exacte")
        self.mock_agent_recherche.recherche_interaction_verbatim.assert_called_with(
            "phrase exacte"
        )

    def test_executer_routing_concept(self):
        """Vérifie le routing 'concept' vers recherche_contexte_memoire_vectorielle."""
        self.mock_agent_recherche.recherche_contexte_memoire_vectorielle.return_value = ResultatRecherche(
            [], 0
        )
        self.tool.executer("concept", "idée floue")
        self.mock_agent_recherche.recherche_contexte_memoire_vectorielle.assert_called_with(
            "idée floue"
        )

    def test_executer_inconnu(self):
        """Vérifie la gestion d'un type de recherche inconnu."""
        res = self.tool.executer("danse_interpretative", "query")
        self.assertIn("error", res)

    # =========================================================================
    # 2. TEST LECTURE FICHIER COMPLET (Physique)
    # =========================================================================

    def test_lire_fichier_complet_succes(self):
        """Vérifie la lecture d'un fichier trouvé physiquement."""
        # 1. Mock de la localisation par AgentRecherche
        self.mock_agent_recherche.localiser_fichiers_physiques.return_value = [
            "/fake/path/test.py"
        ]

        # 2. Mock du système de fichiers (Path)
        with (
            patch("pathlib.Path.is_file", return_value=True),
            patch("pathlib.Path.read_text", return_value="print('hello world')"),
        ):
            res = self.tool.lire_fichier_complet("test.py")

            # Assert : Le contenu lu doit être présent
            self.assertIn("print('hello world')", res)
            # Assert : Le header Markdown doit être ajouté
            self.assertIn("FICHIER", res)

    def test_lire_fichier_complet_introuvable(self):
        """Vérifie le message d'erreur si localiser_fichiers_physiques ne trouve rien."""
        self.mock_agent_recherche.localiser_fichiers_physiques.return_value = []

        res = self.tool.lire_fichier_complet("fantome.py")

        self.assertIn("INTROUVABLE", res)

    def test_lire_fichier_complet_dossier(self):
        """Vérifie le rejet si le chemin pointe vers un dossier."""
        self.mock_agent_recherche.localiser_fichiers_physiques.return_value = [
            "/fake/dir"
        ]

        with patch("pathlib.Path.is_file", return_value=False):
            res = self.tool.lire_fichier_complet("dossier")
            self.assertIn("est un dossier", res)

    # =========================================================================
    # 3. TEST TRAITEMENT BATCH (traiter_recherche_memoire)
    # =========================================================================

    def test_traiter_recherche_memoire_regex(self):
        """Vérifie que la regex découpe bien une demande multiple."""
        # Input : une phrase naturelle contenant deux fichiers
        args = {"query": "regarde script_A.py et aussi config.yaml s'il te plait"}

        # On mock lire_fichier_complet pour éviter la complexité I/O ici
        # Side effect : retourne un contenu fictif pour chaque appel
        with patch.object(
            self.tool, "lire_fichier_complet", side_effect=["ContentA", "ContentB"]
        ) as mock_lire:
            res = self.tool.traiter_recherche_memoire(args)

            # Vérif que la regex a bien isolé les noms
            self.assertEqual(len(res["payload"]), 2)
            self.assertEqual(res["payload"][0].titre, "script_A.py")
            self.assertEqual(res["payload"][1].titre, "config.yaml")

            # Vérif que la méthode de lecture a été appelée 2 fois
            self.assertEqual(mock_lire.call_count, 2)

    # =========================================================================
    # 4. TEST CARTOGRAPHIE
    # =========================================================================

    def test_lecture_cartographie_succes(self):
        """Vérifie la lecture et le formatage du fichier project_map.json."""
        fake_json = json.dumps({"a.py": "desc", "b.py": "desc"})

        # On mock l'existence du fichier et son ouverture
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=fake_json)),
        ):
            res = self.tool.traiter_lecture_cartographie({})

            payload = res["payload"][0]
            self.assertEqual(payload.type, "cartographie_projet")
            # Vérifie le formatage de sortie
            self.assertIn("a.py", payload.contenu)
            self.assertIn("Total fichiers indexés: 2", payload.contenu)

    def test_lecture_cartographie_absente(self):
        """Vérifie le fallback si project_map.json n'existe pas."""
        with patch("pathlib.Path.exists", return_value=False):
            res = self.tool.traiter_lecture_cartographie({})

            payload = res["payload"][0]
            self.assertEqual(payload.type, "erreur_systeme")
            self.assertIn("n'existe pas", payload.contenu)


if __name__ == "__main__":
    unittest.main()
