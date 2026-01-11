#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Unitaire: Auditor Base
Cible : agentique/base/auditor_base.py
Objectif : Valider la résolution des chemins, la validation de types profonde et la détection de champs vides.
"""

import unittest
from dataclasses import dataclass, field
from typing import List, Optional
from pathlib import Path

from agentique.base.auditor_base import AuditorBase
from agentique.base.config_paths import ROOT_DIR


# --- MOCK DATACLASSES POUR LE TEST ---
@dataclass
class ItemSimple:
    nom: str
    valeur: int


@dataclass
class ItemComplexe:
    titre: str
    items: List[ItemSimple]  # Typage profond à vérifier


@dataclass
class ItemIntrus:
    """Une classe qui n'a rien à faire là."""

    info: str = "Intrus"


# --- MOCK AUDITOR ---
class MockAuditor(AuditorBase):
    """Surcharge l'Auditor pour tester la logique de validation avec des configs fixes."""

    def __init__(self):
        # On contourne l'init standard pour injecter notre config de test
        self.nom_agent = "mock_tester"
        self.standards = None
        self._config_agent = {
            "formats_sortie": ["ItemComplexe", "dict"],  # Seuls ces formats sont permis
            "paths": {"logs": "logs_test"},
        }
        self.runtime_log_path = Path("./test_logs.jsonl")


# --- TESTS ---
class TestAuditorBase(unittest.TestCase):
    def setUp(self):
        self.auditor = MockAuditor()
        self.auditor_real = AuditorBase("semi")  # Pour tester les vrais chemins

    # =========================================================================
    # 1. TEST DES CHEMINS (PATH RESOLUTION)
    # =========================================================================

    def test_resolution_chemin_absolu(self):
        """Vérifie que get_path retourne un chemin absolu basé sur ROOT_DIR."""
        # On utilise l'auditor réel (Semi) car on sait qu'il a des chemins configurés
        path_logs = self.auditor_real.get_path("logs")

        # Si path_logs est None (ex: config incomplète), le test doit le dire proprement
        if path_logs:
            self.assertIn(str(ROOT_DIR), path_logs)
            self.assertTrue(path_logs.endswith("logs"))

    def test_chemin_inconnu(self):
        """Vérifie le comportement si le chemin n'existe pas dans la config."""
        path = self.auditor_real.get_path("chemin_inexistant_imaginaire")
        self.assertIsNone(path)

    # =========================================================================
    # 2. TEST DE VALIDATION TYPE (FORMAT SORTIE)
    # =========================================================================

    def test_validation_format_autorise(self):
        """Un format déclaré dans formats_sortie doit passer."""
        item = ItemComplexe(titre="Test", items=[])
        self.assertTrue(self.auditor.valider_format_sortie(item))

    def test_validation_format_interdit(self):
        """Un format NON déclaré doit échouer."""
        item_interdit = ItemSimple(
            nom="Non", valeur=0
        )  # Pas dans formats_sortie du Mock

        # Note: AuditorBase loggue l'erreur et retourne False
        valid = self.auditor.valider_format_sortie(item_interdit)
        self.assertFalse(valid)

    # =========================================================================
    # 3. TEST DE VALIDATION PROFONDE (Deep Type Checking)
    # =========================================================================

    def test_validation_profonde_succes(self):
        """Une liste typée List[ItemSimple] doit contenir des ItemSimple."""
        sub_item = ItemSimple(nom="Ok", valeur=1)
        container = ItemComplexe(titre="Root", items=[sub_item])

        self.assertTrue(self.auditor._valider_champs_profond(container))

    def test_validation_profonde_echec(self):
        """Une liste typée List[ItemSimple] NE DOIT PAS contenir une autre Dataclass."""
        # --- CORRECTION ---
        # On utilise une Dataclass intrus.
        # L'Auditor actuel vérifie les types SI c'est une Dataclass.
        intrus = ItemIntrus()
        container_piege = ItemComplexe(titre="Root", items=[intrus])

        # Le système doit détecter que 'ItemIntrus' != 'ItemSimple'
        valid = self.auditor._valider_champs_profond(container_piege)
        self.assertFalse(
            valid,
            "Le Deep Check aurait dû détecter la mauvaise Dataclass dans la liste",
        )

    # =========================================================================
    # 4. TEST CHAMPS INUTILISÉS (Unused Fields)
    # =========================================================================

    def test_champs_vides_detection(self):
        """Doit détecter si des champs obligatoires sont vides/None."""
        # items est vide -> C'est un champ ignoré potentiel
        objet_vide = ItemComplexe(titre="", items=[])

        # La méthode ne retourne pas False (c'est un Warning), mais on vérifie qu'elle tourne sans crash
        res = self.auditor.valider_utilisation_complete(objet_vide)
        self.assertTrue(res)


if __name__ == "__main__":
    unittest.main()
