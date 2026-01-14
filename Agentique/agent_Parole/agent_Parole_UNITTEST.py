#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Unitaire: Agent Parole
Cible : agentique/sous_agents_gouvernes/agent_Parole/agent_Parole.py
Objectif : Valider l'assemblage des prompts, le formatage des sections et le dispatch dynamique.
"""

import unittest
from unittest.mock import MagicMock, patch, mock_open
from typing import List

from agentique.sous_agents_gouvernes.agent_Parole.agent_Parole import AgentParole
from agentique.base.contrats_interface import (
    StandardPrompt,
    StandardPromptCode,
    ResultatIntention,
    Souvenir,
    Regle,
    FichierReadme,
    CodeChunk,
    ModificateursCognitifs,
    Sujet,
    Action,
    Categorie,
    SearchMode,
)


class TestAgentParole(unittest.TestCase):
    def setUp(self):
        """Préparation de l'environnement de test (Mocking)."""
        self.mock_auditor = MagicMock()
        self.mock_contexte = MagicMock()

        # On simule le chargement de config pour éviter les accès disques
        with patch(
            "agentique.sous_agents_gouvernes.agent_Parole.agent_Parole.AgentParole._charger_config"
        ) as mock_cfg:
            mock_cfg.return_value = {
                "prompts": {"instructions_systeme": "Tu es une IA."}
            }

            # On instancie l'agent sans déclencher les __init__ parents lourds si possible
            # Ici on utilise l'init normal mais avec des mocks
            self.agent = AgentParole(agent_contexte=self.mock_contexte)
            self.agent.auditor = self.mock_auditor  # Injection post-init pour être sûr

        # Données communes pour les tests
        self.intention_base = ResultatIntention(
            prompt="Test",
            sujet=Sujet.SECONDMIND,
            action=Action.PARLER,
            categorie=Categorie.SALUER,
        )
        self.modif_base = ModificateursCognitifs(search_mode=SearchMode.NONE)

        # Mocks des méthodes de lecture disque internes pour isoler le test
        self.agent._recuperer_profil_utilisateur = MagicMock(return_value="Profil Test")
        self.agent._recuperer_resume_systeme = MagicMock(return_value="Resume Test")

    # =========================================================================
    # 1. TEST DU DISPATCHER (Routing)
    # =========================================================================

    def test_dispatcher_standard(self):
        """Vérifie que StandardPrompt déclenche le constructeur standard."""
        req = StandardPrompt(
            prompt_original="Bonjour",
            instructions_systeme="Sys",
            modificateurs=self.modif_base,
            intention=self.intention_base,
            historique=["User: A", "AI: B"],
            contexte_memoire=[
                Souvenir(contenu="Mem", titre="T", type="txt", score=1.0)
            ],
            regles=[Regle(contenu="R1", titre="R1")],
            fichiers_readme=[FichierReadme(contenu="Read", titre="R")],
        )

        # On espionne la méthode privée
        with patch.object(
            self.agent, "_construire_prompt_standard", return_value="PROMPT_OK"
        ) as mock_method:
            res = self.agent.construire_prompt_llm(req)

            mock_method.assert_called_once()
            self.assertIn("PROMPT_OK", res)
            self.assertIn(
                "StandardPrompt", res
            )  # Vérification du marqueur de type ajouté

    def test_dispatcher_code(self):
        """Vérifie que StandardPromptCode déclenche le constructeur code."""
        req = StandardPromptCode(
            prompt_original="Code moi ça",
            instructions_code_prompt="SysCode",
            modificateurs=self.modif_base,
            intention=self.intention_base,
            historique=[],
            regles=[Regle(contenu="R1", titre="R1")],
            fichiers_readme=[FichierReadme(contenu="Read", titre="R")],
            code_chunks=[
                CodeChunk(
                    contenu="print()",
                    chemin="main.py",
                    type="snippet",
                    langage="python",
                )
            ],
        )

        with patch.object(
            self.agent, "_construire_prompt_code", return_value="CODE_OK"
        ) as mock_method:
            res = self.agent.construire_prompt_llm(req)
            mock_method.assert_called_once()
            self.assertIn("CODE_OK", res)

    # =========================================================================
    # 2. TEST DU FORMATAGE (Logique d'assemblage)
    # =========================================================================

    def test_construire_prompt_standard_contenu(self):
        """
        Vérifie que le prompt final contient bien tous les morceaux.
        CORRIGÉ : Template avec placeholders explicites pour que .format() fonctionne.
        """
        req = StandardPrompt(
            prompt_original="Ma Question Critique",
            # CORRECTION ICI : On ajoute {profil_utilisateur} et {instructions_outils}
            instructions_systeme="Tu es SuperAI. {profil_utilisateur} {instructions_outils}",
            modificateurs=self.modif_base,
            intention=self.intention_base,
            historique=["User: Salut", "AI: Hello"],
            contexte_memoire=[
                Souvenir(contenu="InfoImportante", titre="S1", type="txt", score=1.0)
            ],
            regles=[Regle(contenu="Pas de insultes", titre="R1")],
            fichiers_readme=[FichierReadme(contenu="Doc Technique", titre="R")],
        )

        # On simule l'existence physique du fichier outils pour éviter FileNotFoundError
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.read_text", return_value="[INSTRUCTIONS OUTILS MOCK]"),
        ):
            prompt = self.agent._construire_prompt_standard(req)

        # Assertions sur le contenu du texte généré
        self.assertIn("<|im_start|>system", prompt)
        self.assertIn("Tu es SuperAI", prompt)
        self.assertIn(
            "Profil Test", prompt
        )  # Vérifie que {profil_utilisateur} a été remplacé
        self.assertIn(
            "[INSTRUCTIONS OUTILS MOCK]", prompt
        )  # Vérifie que {instructions_outils} a été remplacé

        self.assertIn("InfoImportante", prompt)  # Mémoire présente
        self.assertIn("Pas de insultes", prompt)  # Règle présente
        self.assertIn("Doc Technique", prompt)  # Readme présent

        self.assertIn("Salut", prompt)  # Historique présent
        self.assertIn("Ma Question Critique", prompt)  # Prompt user présent

    def test_formater_historique(self):
        """Vérifie la boucle de formatage de l'historique."""
        histo = ["User: Q1", "AI: R1", "User: Q2"]
        res = self.agent._formater_historique(histo)

        self.assertIn("👤 Utilisateur : User: Q1", res)
        self.assertIn("🤖 Assistant : AI: R1", res)
        # Q2 est orphelin (pas de réponse), il ne devrait pas être affiché ou géré différemment selon la logique
        # Dans votre code actuel : `if i + 1 < len(msgs)` -> Le dernier message user orphelin est ignoré dans l'historique
        # car il est censé être le prompt actuel (géré ailleurs).
        self.assertNotIn("Q2", res)

    def test_formater_code_chunks(self):
        """Vérifie l'injection des snippets de code."""
        chunks = [
            CodeChunk(
                contenu="def a(): pass", chemin="a.py", type="func", langage="python"
            )
        ]
        res = self.agent._formater_code_chunks(chunks)

        self.assertIn("a.py", res)
        self.assertIn("```python", res)
        self.assertIn("def a(): pass", res)

    # =========================================================================
    # 3. TEST DE ROBUSTESSE (Fail-Safe)
    # =========================================================================

    def test_system_prompt_missing_file(self):
        """
        Si instructions_outils.md manque, _formater_system_prompt doit lever une erreur explicite
        (Fail-Fast) ou gérer le cas selon votre politique.
        """
        # On simule l'absence du fichier outil
        with patch("pathlib.Path.exists", return_value=False):
            # Comme vous avez mis un 'raise FileNotFoundError' dans le code, on vérifie qu'il se déclenche.
            with self.assertRaises(FileNotFoundError):
                self.agent._formater_system_prompt("Template {instructions_outils}")


if __name__ == "__main__":
    unittest.main()
