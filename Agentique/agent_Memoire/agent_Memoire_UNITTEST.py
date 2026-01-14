#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Unitaire: Agent Memoire
Cible : agentique/sous_agents_gouvernes/agent_Memoire/agent_Memoire.py
Objectif : Valider la persistance transactionnelle, la ségrégation Narratif/Législatif et le filtrage des artefacts.
"""

import unittest
import json
import os
from unittest.mock import MagicMock, patch, mock_open, call
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass

# Imports des structures de données
from agentique.base.contrats_interface import (
    Interaction,
    MetaData,
    Intention,
    ResultatIntention,
    Sujet,
    Action,
    Categorie,
)
from agentique.sous_agents_gouvernes.agent_Memoire.agent_Memoire import AgentMemoire


class TestAgentMemoire(unittest.TestCase):
    def setUp(self):
        """
        Configuration de l'environnement de test isolé.
        On bypass le __init__ lourd pour injecter manuellement les dépendances (Moteurs & Recherche).
        """
        # 1. Création de l'instance vide (Bypass __init__)
        self.agent = AgentMemoire.__new__(AgentMemoire)

        # 2. Mocks des services de base
        self.agent.nom_agent = "AgentMemoire"
        self.agent.logger = MagicMock()
        self.agent.auditor = MagicMock()
        self.agent.stats_manager = MagicMock()

        # 3. Mocks des Moteurs Vectoriels (Architecture Twin-Engine)
        self.mock_moteur_narratif = MagicMock()
        self.mock_moteur_legislatif = MagicMock()
        self.agent.moteur_vectoriel = self.mock_moteur_narratif
        self.agent.moteur_regles = self.mock_moteur_legislatif

        # 4. Mock de l'Agent Recherche (Indexation Whoosh)
        self.mock_agent_recherche = MagicMock()
        self.agent.agent_recherche = self.mock_agent_recherche

        # 5. Configuration par défaut
        self.agent.config = {
            "artefacts_code": {
                "ignorer_tool_calls": True,  # CRITIQUE pour le test de filtrage
                "extensions_map": {"python": "py", "json": "json"},
            }
        }

        # 6. Configuration des chemins Auditor (Simulés)
        self.agent.auditor.get_path.side_effect = lambda x: f"/fake/path/{x}"

    # =========================================================================
    # 1. TEST SAUVEGARDE BRUTE (Sécurité WAL)
    # =========================================================================

    @patch("os.fsync")  # On vérifie l'atomicité
    def test_sauvegarder_interaction_brute_atomicite(self, mock_fsync):
        """
        Vérifie que la sauvegarde brute force bien l'écriture disque (fsync)
        pour éviter la perte de données en cas de crash.
        """
        # Données factices
        interaction_txt = "User: Hello"

        # Mock de l'ouverture fichier
        m = mock_open()
        with patch("builtins.open", m):
            with patch("pathlib.Path.exists", return_value=True):
                res = self.agent.sauvegarder_interaction_brute(
                    interaction_txt, contenu="Hello"
                )

        # Assertions
        self.assertTrue(res)
        handle = m()
        handle.flush.assert_called()  # Doit flusher le buffer Python
        mock_fsync.assert_called()  # Doit forcer l'OS à écrire sur le disque

    # =========================================================================
    # 2. TEST MEMORISATION ACTIVE (Hot Path)
    # =========================================================================

    def test_memoriser_interaction_workflow_complet(self):
        """
        Vérifie le pipeline complet : Disque -> Moteur Narratif -> Whoosh.
        """
        # --- ARRANGE : Création d'une Interaction complexe ---
        meta = MetaData(timestamp="2025-01-01T12:00:00", session_id="test_sess")
        intent = Intention(
            sujet=Sujet.CODE,
            action=Action.CODER,
            categorie=Categorie.PYTHON,
            analyse=ResultatIntention(
                sujet=Sujet.CODE,
                action=Action.CODER,
                categorie=Categorie.PYTHON,
                score=1.0,
                raison="Test",
            ),
        )
        interaction = Interaction(
            prompt="Code moi un test",
            reponse="Voici le code...",
            meta=meta,
            intention=intent,
        )

        # Mock File System
        with patch("builtins.open", mock_open()) as m_open:
            with patch("pathlib.Path.exists", return_value=True):
                # --- ACT ---
                self.agent.memoriser_interaction(interaction)

        # --- ASSERT ---
        # 1. Validation Auditor
        self.agent.auditor.valider_format_sortie.assert_called_with(interaction)

        # 2. Vectorisation Immédiate (Moteur Narratif)
        self.mock_moteur_narratif.ajouter_fragment.assert_called()
        args_vec, _ = self.mock_moteur_narratif.ajouter_fragment.call_args
        self.assertIn("Voici le code", args_vec[0])  # Le contenu texte concaténé

        # 3. Indexation Whoosh
        self.mock_agent_recherche.update_index.assert_called()
        _, kwargs_idx = self.mock_agent_recherche.update_index.call_args
        self.assertEqual(kwargs_idx["sujet"], "code")  # Vérification nettoyage

    # =========================================================================
    # 3. TEST FILTRAGE CODE (Anti-Pollution)
    # =========================================================================

    def test_sauvegarder_artefacts_tool_calls(self):
        """
        CRITIQUE : Vérifie que les appels d'outils (JSON techniques) ne sont PAS
        sauvegardés comme du code projet.
        """
        # --- ARRANGE ---
        artefacts = [
            {
                "id": "1",
                "langage": "python",
                "contenu": "print('Vrai code')",
                "metadata_analyse": {},  # Structure minimale
            },
            {
                "id": "2",
                "langage": "json",
                "contenu": '{"function": "lire_fichier", "arguments": {"path": "x"}}',
                "metadata_analyse": {},
            },
        ]

        # --- ACT ---
        with patch("builtins.open", mock_open()) as m_file:
            with patch("pathlib.Path.exists", return_value=False):  # Force l'écriture
                with patch("pathlib.Path.mkdir"):
                    self.agent.sauvegarder_artefacts_code(artefacts)

        # --- ASSERT ---
        # On vérifie les appels d'écriture
        # Le fichier 1 (Python) doit être écrit
        # Le fichier 2 (Tool Call) ne doit PAS être écrit

        # Récupération de tous les appels write
        writes = [
            args[0] for call_args in m_file().write.call_args_list for args in call_args
        ]

        # "print('Vrai code')" doit être présent
        self.assertTrue(any("print('Vrai code')" in w for w in writes))

        # Le tool call JSON ne doit pas être présent dans les écritures fichiers
        self.assertFalse(any('"function": "lire_fichier"' in w for w in writes))

        # Log de confirmation
        # On check si le logger a signalé le rejet
        logs = [str(c) for c in self.agent.logger.info.call_args_list]
        self.assertTrue(any("Tool Call détecté" in l for l in logs))

    # =========================================================================
    # 4. TEST SÉGRÉGATION LÉGISLATIVE (Twin-Engine)
    # =========================================================================

    def test_vectoriser_regle_separation(self):
        """
        Vérifie qu'une règle va dans le Moteur LÉGISLATIF et non le Narratif.
        """
        # --- ACT ---
        meta = {"trigger": "ALERTE"}
        self.agent.vectoriser_regle("Ne jamais mentir", meta)

        # --- ASSERT ---
        # 1. Le moteur législatif DOIT être appelé
        self.mock_moteur_legislatif.ajouter_fragment.assert_called_once()

        # 2. Le moteur narratif NE DOIT PAS être appelé pour une règle
        self.mock_moteur_narratif.ajouter_fragment.assert_not_called()

        # 3. Vérification des métadonnées injectées
        args, kwargs = self.mock_moteur_legislatif.ajouter_fragment.call_args
        envoye = kwargs["meta"]
        self.assertEqual(envoye["type"], "regle_gouvernance")


if __name__ == "__main__":
    unittest.main()
