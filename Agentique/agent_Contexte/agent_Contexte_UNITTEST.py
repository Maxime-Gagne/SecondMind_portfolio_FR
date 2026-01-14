#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Unitaire: Agent Contexte
Cible : agentique/sous_agents_gouvernes/agent_Contexte/agent_Contexte.py
Objectif : Valider le pipeline de récupération, le filtrage par le Juge, et les mécanismes de fallback.
"""

import unittest
from unittest.mock import MagicMock, ANY
from typing import List

from agentique.sous_agents_gouvernes.agent_Contexte.agent_Contexte import AgentContexte
from agentique.base.contrats_interface import (
    ResultatIntention,
    ResultatRecherche,
    ResultatContexte,
    Souvenir,
    Regle,
    FichierReadme,
    Sujet,
    Action,
    Categorie,
)


class TestAgentContexte(unittest.TestCase):
    def setUp(self):
        """
        Préparation de l'environnement de test avec Mocks.
        On simule les agents dépendants pour isoler la logique de Contexte.
        """
        # 1. Mocks des dépendances
        self.mock_recherche = MagicMock()
        self.mock_juge = MagicMock()

        # 2. Instanciation (L'init va tenter de charger la config, on va la surcharger juste après)
        # On utilise un try/except car l'auditor pourrait râler sur le fichier config manquant en test
        try:
            self.agent = AgentContexte(
                agent_recherche=self.mock_recherche, agent_juge=self.mock_juge
            )
        except Exception:
            # Si l'init plante (accès disque config), on patch l'instance manuellement
            # C'est du "Monkey Patching" acceptable pour les tests unitaires
            self.agent = AgentContexte.__new__(AgentContexte)
            self.agent.agent_recherche = self.mock_recherche
            self.agent.agent_juge = self.mock_juge
            self.agent.historique_conversation = []
            # On initialise les composants de base hérités de MetaAgent
            super(AgentContexte, self.agent).__init__(nom_agent="AgentContexte")

        # 3. Injection d'une CONFIGURATION DE TEST (Contrôle total)
        self.agent.config = {
            "regles_symboliques": {r"python": "R_PYTHON", r"bug|erreur": "R_DEBUG"},
            "triggers_categories": {
                "sys": r"système|config",
            },
            "tags_prioritaires": ["truth"],
            "seuil_pertinence_juge": 0.5,
            "max_elements_contexte": 3,
            "max_historique_session": 5,
        }
        self.agent.regles_symboliques_map = self.agent.config["regles_symboliques"]
        self.agent.triggers_categories = self.agent.config["triggers_categories"]

        # 4. Données communes
        self.intention_base = ResultatIntention(
            prompt="J'ai une erreur python",
            sujet=Sujet.SCRIPT,
            action=Action.DEBUG,
            categorie=Categorie.ANALYSER,
        )

    def test_pipeline_complet_nominal(self):
        """
        SCÉNARIO 1 : Tout fonctionne.
        Vérifie que les règles symboliques, sémantiques et la doc sont bien agrégées.
        """
        # --- ARRANGE ---
        # Mock des retours de l'Agent Recherche
        self.mock_recherche.rechercher_regles.side_effect = lambda x: [
            Regle(contenu=f"Contenu {x}", titre=str(x))
        ]
        self.mock_recherche.rechercher_regles_semantiques.return_value = [
            Regle(contenu="Semantique", titre="R_SEM")
        ]
        self.mock_recherche.rechercher_readme.return_value = [
            FichierReadme(contenu="Doc", titre="README.md")
        ]

        # Le juge valide tout (score 1.0)
        self.mock_juge.calculer_pertinence_semantique.return_value = 1.0

        entree_rag = ResultatRecherche(
            souvenirs_bruts=[
                Souvenir(contenu="Memory", titre="M1", type="txt", score=0.5)
            ],
            nb_fichiers_scannes=1,
            temps_recherche=0.1,
        )

        # --- ACT ---
        resultat = self.agent.recuperer_contexte_intelligent(
            resultat_intention=self.intention_base, resultat_recherche=entree_rag
        )

        # --- ASSERT ---
        self.assertIsInstance(resultat, ResultatContexte)

        # Vérif Règles : R_PYTHON + R_DEBUG (via prompt "erreur python") + R_SEM + TRUTH
        titres_regles = [r.titre for r in resultat.regles_actives]
        self.assertIn("R_PYTHON", titres_regles)
        self.assertIn("R_DEBUG", titres_regles)
        self.assertIn("R_SEM", titres_regles)

        # Vérif Doc
        self.assertEqual(resultat.fichiers_readme[0].titre, "README.md")

        # Vérif Mémoire
        self.assertEqual(resultat.contexte_memoire[0].titre, "M1")

    def test_filtrage_juge(self):
        """
        SCÉNARIO 2 : Le Juge filtre les mauvais souvenirs.
        Seuil configuré à 0.5. On envoie un souvenir à 0.9 et un à 0.1.
        """
        # --- ARRANGE ---
        s_bon = Souvenir(contenu="Bon", titre="GOOD", type="txt", score=0.0)
        s_mauvais = Souvenir(contenu="Mauvais", titre="BAD", type="txt", score=0.0)

        entree_rag = ResultatRecherche(
            souvenirs_bruts=[s_bon, s_mauvais],
            nb_fichiers_scannes=2,
            temps_recherche=0.1,
        )

        # Simulation Juge : Good -> 0.9, Bad -> 0.1
        def mock_eval(prompt, contenu, titre, contexte):
            return 0.9 if titre == "GOOD" else 0.1

        self.mock_juge.calculer_pertinence_semantique.side_effect = mock_eval

        # Mocks par défaut pour éviter crash sur les autres parties
        self.mock_recherche.rechercher_regles.return_value = []
        self.mock_recherche.rechercher_regles_semantiques.return_value = []
        self.mock_recherche.rechercher_readme.return_value = []

        # --- ACT ---
        resultat = self.agent.recuperer_contexte_intelligent(
            self.intention_base, entree_rag
        )

        # --- ASSERT ---
        # Seul le GOOD doit rester
        self.assertEqual(len(resultat.contexte_memoire), 1)
        self.assertEqual(resultat.contexte_memoire[0].titre, "GOOD")
        self.assertGreaterEqual(resultat.contexte_memoire[0].score, 0.5)

    def test_fallbacks_total(self):
        """
        SCÉNARIO 3 : Tout est vide (Recherche échouée).
        L'agent doit injecter des objets par défaut pour éviter les erreurs.
        """
        # --- ARRANGE ---
        # Tout retourne vide
        self.mock_recherche.rechercher_regles.return_value = []
        self.mock_recherche.rechercher_regles_semantiques.return_value = []
        self.mock_recherche.rechercher_readme.return_value = []

        entree_vide = ResultatRecherche(
            souvenirs_bruts=[], nb_fichiers_scannes=0, temps_recherche=0.0
        )

        # --- ACT ---
        resultat = self.agent.recuperer_contexte_intelligent(
            self.intention_base, entree_vide
        )

        # --- ASSERT ---
        # 1. Règle Fallback
        self.assertTrue(
            any("DEFAULT" in r.titre for r in resultat.regles_actives),
            "Règle par défaut manquante",
        )

        # 2. Doc Fallback (FichierReadme neutre)
        self.assertTrue(
            any("NEANT" in d.titre for d in resultat.fichiers_readme),
            "Doc par défaut manquante",
        )

        # 3. Mémoire Fallback
        self.assertTrue(
            any("MEMOIRE_VIDE" in s.titre for s in resultat.contexte_memoire),
            "Souvenir par défaut manquant",
        )

    def test_historique_rotation(self):
        """
        SCÉNARIO 4 : Gestion de l'historique.
        Vérifie que la limite 'max_historique_session' (5 dans setUp) est respectée.
        """
        # On ajoute 10 messages (5 paires user/ai)
        for i in range(10):
            self.agent.mettre_a_jour_historique(f"User {i}", f"AI {i}")

        # La config dit max 5. Comme on stocke [User, AI], ça fait 5 lignes au total ?
        # Vérifions la logique de l'agent :
        # self.historique_conversation.append(prompt) -> +1
        # self.historique_conversation.append(reponse) -> +1
        # Donc pour 10 tours -> 20 items.
        # Si max_historique_session = 5 items.

        histo = self.agent.get_historique_chat()
        self.assertEqual(len(histo), 5)

        # On vérifie que ce sont bien les DERNIERS messages
        self.assertIn("AI 9", histo[-1])


if __name__ == "__main__":
    unittest.main()
