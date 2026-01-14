#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Unitaire: META Agent & Memoire RAM
Cible : agentique/base/META_agent.py
Objectif : Valider l'injection de dépendances, l'instrumentation automatique (Stats) et le Singleton RAM.
"""

import unittest
from agentique.base.META_agent import MetaAgent, AgentBase, MemoireTravailRAM
from agentique.base.contrats_interface import StatsBase


class TestMemoireTravailRAM(unittest.TestCase):
    """Teste le comportement Singleton et la gestion de la mémoire volatile."""

    def setUp(self):
        """Nettoyage avant chaque test pour garantir l'isolation malgré le Singleton."""
        self.memoire = MemoireTravailRAM()
        self.memoire.vider_travail()
        # On reset aussi les stats internes du singleton pour le test
        if hasattr(self.memoire, "stats"):
            self.memoire.stats = {k: 0 for k in self.memoire.stats}

    def test_singleton_identity(self):
        """Vérifie que deux instanciations renvoient le MÊME objet en mémoire."""
        m1 = MemoireTravailRAM()
        m2 = MemoireTravailRAM()
        self.assertIs(m1, m2, "MemoireTravailRAM doit être un Singleton strict.")

        # Vérification partage d'état
        m1.ajouter_travail({"contenu": "test"})
        self.assertEqual(len(m2.recuperer_travail()), 1)

    def test_validation_ajout(self):
        """Vérifie que seuls les dictionnaires valides sont acceptés."""
        # Cas invalide (String)
        res_str = self.memoire.ajouter_travail("Pas un dict")
        self.assertFalse(res_str)

        # Cas invalide (Dict sans clé 'contenu')
        res_key = self.memoire.ajouter_travail({"titre": "Pas de contenu"})
        self.assertFalse(res_key)

        # Cas valide
        res_ok = self.memoire.ajouter_travail({"contenu": "Valide"})
        self.assertTrue(res_ok)


class TestMetaAgentInstrumentation(unittest.TestCase):
    """Teste la magie noire de la métaclasse (Injection & Wrapping)."""

    def setUp(self):
        # On définit une classe Agent "Bidon" qui utilise MetaAgent
        # Cela permet de tester l'instrumentation sans dépendre des vrais agents complexes
        class AgentTest(AgentBase):
            def methode_succes(self):
                return "OK"

            def methode_echec(self):
                raise ValueError("Boom")

            def _methode_privee(self):
                return "Secret"

        self.AgentTestClass = AgentTest
        self.agent = self.AgentTestClass(nom_agent="AgentTest")

        # Reset des stats pour être propre
        self.agent.stats_manager.reinitialiser()

    def test_injection_dependances(self):
        """Vérifie que MetaAgent a bien injecté les outils."""
        self.assertTrue(hasattr(self.agent, "auditor"), "Auditor manquant")
        self.assertTrue(hasattr(self.agent, "stats_manager"), "StatsManager manquant")
        self.assertTrue(hasattr(self.agent, "logger"), "CognitiveLogger manquant")

        # Vérification des méthodes utilitaires injectées
        self.assertTrue(hasattr(self.agent, "calculer_pertinence"))
        self.assertTrue(hasattr(self.agent, "valider_echange"))

    def test_instrumentation_succes(self):
        """Vérifie qu'appeler une méthode compte bien dans les stats."""
        # État avant
        self.assertEqual(self.agent.stats_manager.appels_total, 0)

        # Action
        resultat = self.agent.methode_succes()

        # Vérifications
        self.assertEqual(resultat, "OK")  # Le comportement d'origine est préservé
        self.assertEqual(self.agent.stats_manager.appels_total, 1)  # +1 appel global

        # Vérification stat spécifique
        specifiques = self.agent.stats_manager.stats_specifiques
        self.assertEqual(specifiques.get("appels_methode_succes"), 1)

    def test_instrumentation_echec(self):
        """Vérifie que les exceptions sont comptées comme erreurs mais bien levées."""
        # On s'attend à ce que l'erreur remonte (fail-fast)
        with self.assertRaises(ValueError):
            self.agent.methode_echec()

        # Mais on veut qu'elle soit comptabilisée dans les stats avant de planter
        self.assertEqual(self.agent.stats_manager.appels_total, 1)
        self.assertEqual(self.agent.stats_manager.erreurs_total, 1)
        self.assertEqual(
            self.agent.stats_manager.stats_specifiques.get("erreurs_methode_echec"), 1
        )

    def test_ignore_methodes_privees(self):
        """MetaAgent ne doit pas wrapper les méthodes commençant par _."""
        # On appelle la méthode privée
        self.agent._methode_privee()

        # Les stats NE DOIVENT PAS bouger
        self.assertEqual(self.agent.stats_manager.appels_total, 0)


if __name__ == "__main__":
    unittest.main()
