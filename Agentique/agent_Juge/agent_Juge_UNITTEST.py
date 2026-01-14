#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Unitaire: Agent Juge
Cible : agentique/sous_agents_gouvernes/agent_Juge/agent_Juge.py
Objectif : Valider le scoring de pertinence, le parsing robuste du JSON LLM et les garde-fous.
"""

import unittest
from unittest.mock import MagicMock
from typing import Dict

from agentique.sous_agents_gouvernes.agent_Juge.agent_Juge import AgentJuge
from agentique.base.contrats_interface import ResultatJuge


class TestAgentJuge(unittest.TestCase):
    def setUp(self):
        """
        Préparation de l'environnement de test avec Mocks.
        On isole le Juge de l'API réelle du LLM et du disque.
        """
        # 1. Mocks des dépendances
        self.mock_recherche = MagicMock()
        self.mock_mini_llm = MagicMock()

        # 2. Instanciation (Bypass partiel de l'init lourd)
        try:
            self.agent = AgentJuge(
                agent_recherche=self.mock_recherche, moteur_mini_llm=self.mock_mini_llm
            )
        except Exception:
            # Fallback si l'auditor râle sur les chemins
            self.agent = AgentJuge.__new__(AgentJuge)
            self.agent.agent_recherche = self.mock_recherche
            self.agent.moteur_mini_llm = self.mock_mini_llm
            super(AgentJuge, self.agent).__init__(nom_agent="AgentJuge")

        # 3. Injection CONFIGURATION DE TEST (Contrôle total des seuils)
        self.agent.config = {
            "pertinence": {
                "stop_words": ["le", "la", "de", "un", "une", "est"],
                "boost_titre": 1.2,
                "bonus_sujet": 0.1,
            },
            "decision": {"seuil_validation": 0.7},
            "min_chars_contexte": 10,
            "max_chars_contexte": 100,  # Très court pour tester la troncature
            # CORRECTION : Marge suffisante pour contenir le System Prompt (~500 chars)
            "marge_prompt_total": 2000,
        }
        # Mapping des sous-configs pour que l'agent les trouve
        self.agent.cfg_limites = self.agent.config
        self.agent.cfg_decision = self.agent.config["decision"]
        self.agent.cfg_pertinence = self.agent.config["pertinence"]

    # =========================================================================
    # 1. TEST PERTINENCE (Algorithmique Pure)
    # =========================================================================

    def test_pertinence_nominale(self):
        """Vérifie qu'un mot-clé présent donne un score positif."""
        score = self.agent.calculer_pertinence_semantique(
            prompt="Erreur Python",
            souvenir_contenu="Voici comment fixer une erreur Python",
            souvenir_titre="Doc Python",
            filtres_semantiques=[],
        )
        self.assertGreater(
            score, 0.5, "Le score devrait être élevé pour une correspondance exacte"
        )

    def test_pertinence_stop_words(self):
        """Vérifie que les mots vides sont ignorés."""
        # Prompt composé uniquement de stop words
        score = self.agent.calculer_pertinence_semantique(
            prompt="le la de",
            souvenir_contenu="le la de",
            souvenir_titre="le",
            filtres_semantiques=[],
        )
        self.assertEqual(
            score, 0.0, "Les stop words seuls ne doivent pas générer de pertinence"
        )

    def test_pertinence_boost_titre(self):
        """Vérifie que la présence dans le titre augmente le score."""
        score_contenu_seul = self.agent.calculer_pertinence_semantique(
            prompt="Important",
            souvenir_contenu="Ceci est important",
            souvenir_titre="Autre",
            filtres_semantiques=[],
        )

        score_avec_titre = self.agent.calculer_pertinence_semantique(
            prompt="Important",
            souvenir_contenu="Ceci est important",
            souvenir_titre="Important Doc",  # Match titre
            filtres_semantiques=[],
        )

        # Le boost titre (1.2) + logique Max devrait rendre le score titre supérieur ou égal
        self.assertGreaterEqual(score_avec_titre, score_contenu_seul)

    # =========================================================================
    # 2. TEST COHÉRENCE (Pipeline LLM)
    # =========================================================================

    def test_coherence_nominale(self):
        """
        SCÉNARIO 1 : Le LLM répond un JSON valide.
        """
        # --- ARRANGE ---
        self.mock_mini_llm.generer.return_value = {
            "response": '{"score": 1.0, "raison": "Tout est correct"}'
        }

        # --- ACT ---
        # Contexte > 10 chars
        res = self.agent.evaluer_coherence_reponse(
            contexte_rag_str="Paris est en France depuis longtemps.",
            prompt="Où est Paris ?",
            reponse="Paris est en France.",
        )

        # --- ASSERT ---
        self.assertIsInstance(res, ResultatJuge)
        self.assertEqual(res.score, 1.0)
        self.assertTrue(res.valide)
        self.assertEqual(res.raison, "Tout est correct")

    def test_coherence_json_bruite(self):
        """
        SCÉNARIO 2 : Le LLM est bavard (Texte autour du JSON).
        C'est le test le plus important pour la robustesse.
        """
        # --- ARRANGE ---
        raw_response = """
        Voici l'analyse demandée :
        ```json
        {
            "score": 0.2,
            "raison": "Hallucination détectée"
        }
        ```
        J'espère que ça aide.
        """
        self.mock_mini_llm.generer.return_value = {"response": raw_response}

        # --- ACT ---
        # Contexte > 10 chars pour passer le filtre
        res = self.agent.evaluer_coherence_reponse(
            contexte_rag_str="Contexte suffisamment long pour le test.",
            prompt="Q",
            reponse="R",
        )

        # --- ASSERT ---
        self.assertEqual(res.score, 0.2)
        self.assertFalse(res.valide)  # Seuil à 0.7 dans setUp
        self.assertEqual(res.raison, "Hallucination détectée")

    def test_contexte_vide_abstention(self):
        """
        SCÉNARIO 3 : Pas de contexte fourni.
        Le juge doit s'abstenir (Score 0.5) sans appeler le LLM.
        """
        # --- ACT ---
        res = self.agent.evaluer_coherence_reponse(
            contexte_rag_str="",  # Vide
            prompt="Q",
            reponse="R",
        )

        # --- ASSERT ---
        self.mock_mini_llm.generer.assert_not_called()  # Économie de ressources
        self.assertEqual(res.score, 0.5)
        self.assertIn("vide", res.raison)

    def test_truncature_contexte(self):
        """
        SCÉNARIO 4 : Contexte trop long.
        L'agent doit couper le texte pour éviter le crash du LLM.
        """
        # --- ARRANGE ---
        # On génère un texte de 200 chars (max configuré à 100 dans setUp)
        long_contexte = "A" * 200

        self.mock_mini_llm.generer.return_value = {"response": '{"score": 1.0}'}

        # --- ACT ---
        self.agent.evaluer_coherence_reponse(long_contexte, "Q", "R")

        # --- ASSERT ---
        # On récupère l'argument passé à generer()
        args, _ = self.mock_mini_llm.generer.call_args
        prompt_envoye = args[0]

        # Le prompt ne doit pas contenir les 200 'A' d'affilée
        self.assertNotIn("A" * 150, prompt_envoye)
        # Mais il doit contenir le marqueur de coupe
        self.assertIn("TRONQUÉ", prompt_envoye)

    def test_json_reparation_backslashes(self):
        """
        SCÉNARIO 5 : JSON cassé par des chemins Windows (Backslashes).
        """
        # JSON invalide à cause du \U non échappé
        bad_json = '{"score": 1.0, "raison": "Fichier C:\\User\\Test"}'

        # --- ACT ---
        data = self.agent._extraire_json_reponse(bad_json)

        # --- ASSERT ---
        self.assertEqual(data.get("score"), 1.0)
        self.assertIn("User", data.get("raison"))


if __name__ == "__main__":
    unittest.main()
