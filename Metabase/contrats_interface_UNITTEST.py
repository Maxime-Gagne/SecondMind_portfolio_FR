#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Unitaire: Contrats d'Interface
Cible : agentique/base/contrats_interface.py
Objectif : Valider les types, les valeurs par défaut et les garde-fous (__post_init__).
"""

import unittest
from datetime import datetime
from agentique.base.contrats_interface import (
    # Enums
    Sujet,
    Action,
    Categorie,
    # Atomes
    Souvenir,
    Regle,
    FichierReadme,
    # Résultats
    ResultatIntention,
    ResultatRecherche,
    ResultatContexte,
    ResultatJuge,
    # Prompts
    StandardPrompt,
    StandardPromptCode,
    ManualContextCodePrompt,
    MemorySearchPrompt,
    MemorySearchFirstPrompt,
    CartographyPrompt,
    FileInspectionPrompt,
    WebSearchPrompt,
    ProtocolePrompt,
    ModificateursCognitifs,
    # Code
    CodeChunk,
    ResultatCode,
    # Stats
    StatsBase,
)


class TestContratsInterface(unittest.TestCase):
    def setUp(self):
        """Configuration commune pour les tests."""
        self.modifs_base = ModificateursCognitifs(search_mode="auto")
        self.intention_base = ResultatIntention(
            prompt="Test",
            sujet=Sujet.SECONDMIND,
            action=Action.DEBUG,
            categorie=Categorie.TEST,
        )
        self.souvenir_base = Souvenir(contenu="Info", titre="S1", type="txt", score=1.0)
        self.regle_base = Regle(contenu="Loi", titre="R1")
        self.readme_base = FichierReadme(contenu="Doc", titre="Read")

    # =========================================================================
    # 1. ATOMES & ENUMS
    # =========================================================================

    def test_souvenir_nominal(self):
        s = Souvenir(contenu="Test", titre="T1", type="memo", score=0.9)
        self.assertEqual(s.titre, "T1")
        self.assertEqual(s.score, 0.9)

    def test_regle_defaults(self):
        """Vérifie que le score par défaut d'une règle est bien 10.0 (Prioritaire)."""
        r = Regle(contenu="Interdit", titre="R01")
        self.assertEqual(r.score, 10.0)
        self.assertEqual(r.type, "regle")

    # =========================================================================
    # 2. RÉSULTATS (Sorties Agents)
    # =========================================================================

    def test_resultat_intention_validation(self):
        """Vérifie les garde-fous de ResultatIntention."""
        # Prompt vide
        with self.assertRaises(ValueError):
            ResultatIntention(
                prompt="",
                sujet=Sujet.SECONDMIND,
                action=Action.FAIRE,
                categorie=Categorie.AUTRE,
            )

        # Mauvais types (Enum requis)
        with self.assertRaises(TypeError):
            ResultatIntention(
                prompt="Test",
                sujet="StringInvalide",
                action=Action.FAIRE,
                categorie=Categorie.AUTRE,
            )

    def test_resultat_recherche_validation(self):
        """Vérifie la cohérence des nombres."""
        # Temps négatif
        with self.assertRaises(ValueError):
            ResultatRecherche(
                souvenirs_bruts=[], nb_fichiers_scannes=5, temps_recherche=-1.0
            )

    def test_resultat_contexte_validation(self):
        """Vérifie qu'on ne peut pas créer un contexte vide."""
        with self.assertRaisesRegex(ValueError, "contexte_memoire vide"):
            ResultatContexte(
                contexte_memoire=[],  # Vide interdit
                regles_actives=[self.regle_base],
                historique=[],
                fichiers_readme=[self.readme_base],
                intention_detectee=self.intention_base,
            )

    def test_resultat_juge_validation(self):
        """Vérifie les scores et types du Juge."""
        # Score hors limite
        with self.assertRaises(ValueError):
            ResultatJuge(valide=True, score=6.0, raison="Trop fort", details={})

        # Raison vide
        with self.assertRaises(ValueError):
            ResultatJuge(valide=True, score=5.0, raison="", details={})

    # =========================================================================
    # 3. PROMPTS (AgentParole)
    # =========================================================================

    def test_standard_prompt_validation(self):
        """StandardPrompt doit rejeter les listes vides."""
        with self.assertRaisesRegex(ValueError, "Liste 'contexte_memoire' vide"):
            StandardPrompt(
                prompt_original="Hello",
                instructions_systeme="Sys",
                modificateurs=self.modifs_base,
                intention=self.intention_base,
                historique=[],
                contexte_memoire=[],  # Vide -> Crash attendu
                regles=[self.regle_base],
                fichiers_readme=[self.readme_base],
            )

    def test_memory_search_first_prompt(self):
        """MemorySearchFirstPrompt doit avoir des résultats."""
        with self.assertRaisesRegex(ValueError, "resultats_memoire vide"):
            MemorySearchFirstPrompt(
                prompt_original="Test",
                instructions_first_search="Go",
                resultats_memoire=[],  # Vide
                intention=self.intention_base,
            )

    def test_file_inspection_prompt(self):
        """FileInspectionPrompt doit avoir un fichier valide."""
        fichier_vide = Souvenir(contenu="", titre="Vide", type="file", score=1.0)

        with self.assertRaisesRegex(ValueError, "Aucun fichier sur l'établi"):
            FileInspectionPrompt(
                prompt_original="Check",
                instructions_inspection="Check",
                fichier_en_cours=fichier_vide,  # Contenu vide
                notes_precedentes="Notes",
                intention=self.intention_base,
            )

    def test_web_search_prompt(self):
        """WebSearchPrompt doit avoir une query et des résultats."""
        with self.assertRaises(ValueError):
            WebSearchPrompt(
                query="",
                instructions_web_search_prompt="Inst",
                resultats_web=[{"t": "1"}],
            )

    # =========================================================================
    # 4. LOGIQUE & STATS
    # =========================================================================

    def test_stats_base_increment(self):
        """Vérifie la logique de comptage des stats."""
        stats = StatsBase(nom_agent="TestAgent")

        # État initial
        self.assertEqual(stats.appels_total, 0)

        # Incrément standard
        stats.incrementer_appel()
        self.assertEqual(stats.appels_total, 1)
        self.assertIsNotNone(stats.derniere_execution)

        # Incrément spécifique
        stats.incrementer_stat_specifique("vectorisation")
        self.assertEqual(stats.obtenir_stat_specifique("vectorisation"), 1)

        # Calcul taux
        stats.incrementer_erreur()  # 1 appel, 1 erreur -> 0% réussite
        res = stats.obtenir_statistiques()
        self.assertEqual(res["erreurs_total"], 1)
        self.assertEqual(res["taux_reussite"], 0.0)

    def test_prompt_mixin_unused_fields(self):
        """Vérifie la détection des champs inutilisés (Mixin)."""
        prompt = StandardPrompt(
            prompt_original="Test",
            instructions_systeme="Sys",
            modificateurs=self.modifs_base,
            intention=self.intention_base,
            historique=[],  # Liste vide -> Doit être détectée comme unused
            contexte_memoire=[self.souvenir_base],
            regles=[self.regle_base],
            fichiers_readme=[self.readme_base],
        )
        unused = prompt.get_unused_fields()
        self.assertIn("historique", unused)
        self.assertNotIn("prompt_original", unused)


if __name__ == "__main__":
    unittest.main()
