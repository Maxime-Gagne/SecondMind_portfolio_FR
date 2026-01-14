#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Unitaire: Agent Entraineur
Cible : agentique/sous_agents_gouvernes/agent_Entraineur/agent_Entraineur.py
Objectif : Valider le pipeline d'ingestion de données, le mapping des labels et la boucle d'entraînement (Mockée).
"""

import unittest
import shutil
import json
import torch
import torch.nn as nn
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path

# On importe la classe à tester (adaptation des imports selon ta structure)
from agentique.sous_agents_gouvernes.agent_Entraineur.agent_Entraineur import (
    AgentEntraineur,
    ClassifierHead,
    IntentDataset,
)


class TestAgentEntraineur(unittest.TestCase):
    def setUp(self):
        """
        Préparation de l'environnement de test.
        On utilise des Mocks pour SBERT et le Système de Fichiers.
        """
        # 1. Mock de l'Audit et Config
        self.mock_auditor = MagicMock()
        # Simulation d'une config chargée depuis YAML
        self.fake_config = {
            "chemins": {
                "base_data": "MEMOIRE_TEST/data",
                "datasets": ["dataset_v1.jsonl"],
                "registre_labels": "MEMOIRE_TEST/labels_map.json",
                "output_models": "MEMOIRE_TEST/models",
            },
            "sbert": {"model_path": "fake/path/sbert", "device": "cpu"},
            "entrainement": {"epochs": 1, "learning_rate": 0.01, "hidden_dim": 10},
        }

        # 2. Mock du chargement JSON (Label Map)
        self.fake_labels = {
            "Sujet": {"0": "SUJET.CODE", "1": "SUJET.PHILOSOPHIE"},
            "Action": {"0": "ACTION.PARLER", "1": "ACTION.CODER"},
            "Categorie": {"0": "CATEGORIE.PYTHON", "1": "CATEGORIE.C++"},
        }

        # 3. Patching des méthodes lourdes (Init SBERT, Load Config)
        with (
            patch(
                "agentique.sous_agents_gouvernes.agent_Entraineur.agent_Entraineur.SentenceTransformer"
            ) as MockSbert,
            patch("builtins.open", mock_open(read_data=json.dumps(self.fake_labels))),
            patch.object(
                AgentEntraineur, "_charger_config", return_value=self.fake_config
            ),
        ):
            # Instanciation sécurisée
            self.agent = AgentEntraineur()

            # Injection du Mock SBERT
            self.agent.sbert = MockSbert.return_value
            # Configuration du Mock SBERT pour retourner des vecteurs bidons
            self.agent.sbert.encode.return_value = [0.1] * 384  # Vecteur dimension 384
            self.agent.sbert.get_sentence_embedding_dimension.return_value = 384

            # Injection manuelle output_dir pour éviter erreur Path
            self.agent.output_dir = Path("MEMOIRE_TEST/models")

            # Création dossier temporaire pour simuler sauvegarde
            if not Path("MEMOIRE_TEST").exists():
                Path("MEMOIRE_TEST/models").mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Nettoyage après test"""
        if Path("MEMOIRE_TEST").exists():
            shutil.rmtree("MEMOIRE_TEST")

    # =========================================================================
    # 1. TEST PRÉPARATION DES DONNÉES (Ingestion & Mapping)
    # =========================================================================

    def test_fusionner_datasets_deduplication(self):
        """Vérifie que les prompts doublons sont éliminés."""
        # Simulation de contenu fichier JSONL avec doublons
        fake_jsonl = """
        {"prompt": "Test unique", "sujet": "SUJET.CODE"}
        {"prompt": "Doublon", "sujet": "SUJET.CODE"}
        {"prompt": "Doublon", "sujet": "SUJET.AUTRE"}
        """

        # Mock de Path.read_text
        with (
            patch("pathlib.Path.read_text", return_value=fake_jsonl),
            patch("pathlib.Path.exists", return_value=True),
        ):
            data = self.agent._fusionner_datasets()

            # Doit en rester 2 (Test unique + 1 seul Doublon)
            self.assertEqual(len(data), 2)
            prompts = [d["prompt"] for d in data]
            self.assertIn("Test unique", prompts)
            self.assertEqual(prompts.count("Doublon"), 1)

    def test_preparer_mapping_labels(self):
        """Vérifie que le mapping JSON -> ID Int est correct."""
        # Test pour l'axe "sujet" (Notez la minuscule en entrée)
        mapping = self.agent._preparer_mapping_labels("sujet")

        # Doit correspondre à self.fake_labels["Sujet"]
        # {"SUJET.CODE": 0, "SUJET.PHILOSOPHIE": 1}
        self.assertEqual(mapping["SUJET.CODE"], 0)
        self.assertEqual(mapping["SUJET.PHILOSOPHIE"], 1)
        self.assertEqual(len(mapping), 2)

    # =========================================================================
    # 2. TEST MODÈLE NEURONAL (ClassifierHead)
    # =========================================================================

    def test_classifier_head_structure(self):
        """Vérifie que le réseau de neurones a la bonne forme."""
        model = ClassifierHead(emb_dim=384, hidden_dim=256, nb_labels=3)

        # Test Input (Batch=1, Dim=384)
        fake_input = torch.randn(1, 384)
        output = model(fake_input)

        # Output doit être (Batch=1, Labels=3)
        self.assertEqual(output.shape, (1, 3))

    # =========================================================================
    # 3. TEST BOUCLE D'ENTRAÎNEMENT (Mockée)
    # =========================================================================

    @patch("torch.save")  # On empêche l'écriture réelle du .pth
    def test_entrainer_axe_cycle_complet(self, mock_save):
        """
        Simule un cycle d'entraînement complet sur un axe.
        Vérifie que PyTorch est bien appelé et que le modèle est sauvegardé.
        """
        # --- ARRANGE ---
        # Dataset minimaliste
        data = [
            {"prompt": "Code python", "sujet": "SUJET.CODE"},
            {"prompt": "Philo", "sujet": "SUJET.PHILOSOPHIE"},
        ] * 10  # Dupliqué pour avoir assez de données pour le split

        # Mocking DataLoader pour éviter overhead
        # Mais ici on laisse le DataLoader réel travailler sur des Tensors CPU légers, c'est rapide.

        # --- ACT ---
        # On force epoch=1 et lr=0.01 via la config du setUp
        acc = self.agent._entrainer_axe("sujet", data)

        # --- ASSERT ---
        # 1. Une précision a été retournée
        self.assertIsInstance(acc, float)
        self.assertTrue(0.0 <= acc <= 1.0)

        # 2. SBERT encode a été appelé
        self.agent.sbert.encode.assert_called()

        # 3. Torch Save a été appelé à la fin
        mock_save.assert_called_once()
        args, _ = mock_save.call_args
        # Vérifie que c'est bien le state_dict qui est sauvegardé
        self.assertIsInstance(args[0], dict)
        # Vérifie le nom du fichier
        self.assertIn("classifier_sujet.pth", str(args[1]))

    def test_dataset_trop_petit(self):
        """Vérifie que l'entraînement s'annule si pas assez de données."""
        with patch(
            "agentique.sous_agents_gouvernes.agent_Entraineur.agent_Entraineur.AgentEntraineur._fusionner_datasets"
        ) as mock_fusion:
            mock_fusion.return_value = [{"prompt": "Seul"}]  # 1 seul item

            result = self.agent.entrainer_sur_disque()

            self.assertFalse(result, "Doit retourner False pour dataset insuffisant")


if __name__ == "__main__":
    unittest.main()
