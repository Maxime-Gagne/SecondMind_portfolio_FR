#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agent_Recherche_UNITTEST.py
Unit tests (unittest + mocks) for AgentRecherche.

Notes:
- These tests avoid calling AgentRecherche.__init__ (which performs real I/O)
  by instantiating with __new__ and manually injecting dependencies.
- Adjust the import path of AgentRecherche if your package layout differs.
"""

import json
import os
import shlex
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, mock_open

# ----------------------------
# Imports from your project
# ----------------------------
try:
    # Adjust if needed:
    # from agentique.sous_agents_gouvernes.agent_Recherche.agent_Recherche import AgentRecherche
    from agent_Recherche import AgentRecherche  # if tests are run from same folder
except Exception:
    AgentRecherche = None

try:
    from agentique.base.contrats_interface import Souvenir, Regle, ResultatRecherche
except Exception:
    Souvenir = Regle = ResultatRecherche = None


def _skip_if_missing():
    return (
        AgentRecherche is None
        or Souvenir is None
        or Regle is None
        or ResultatRecherche is None
    )


class AgentRechercheUnitTestBase(unittest.TestCase):
    """Helper base to build an AgentRecherche instance without __init__."""

    def make_agent(self):
        if _skip_if_missing():
            self.skipTest(
                "Project imports not available (AgentRecherche / contrats_interface)."
            )

        agent = AgentRecherche.__new__(AgentRecherche)

        # Minimal injection
        agent.logger = MagicMock()
        agent.auditor = MagicMock()

        # Minimal config defaults used by tested methods
        agent.conf_moteur = {
            "limites": {
                "recherche_everything_max": 20,
                "resultats_finaux": 10,
                "historique_recent": 5,
            },
            "scoring": {"boost_intention": 0.5},
        }

        # Everything executable path
        agent.chemin_executable_everything = "es.exe"

        # Paths for whoosh (only if needed; usually mocked)
        agent.chemin_index_whoosh = Path(os.getcwd()) / "_tmp_whoosh_index"

        # Dependencies optionally used
        agent.agent_memoire = None
        agent.moteur_vectoriel = None

        return agent


@unittest.skipIf(_skip_if_missing(), "Project imports not available.")
class TestExecuterEverything(AgentRechercheUnitTestBase):
    def test_executer_everything_limit_none_uses_config(self):
        agent = self.make_agent()
        agent.conf_moteur["limites"]["recherche_everything_max"] = 77

        with patch("subprocess.run") as sp_run:
            sp_run.return_value = SimpleNamespace(
                stdout="C:\\a.txt\nC:\\b.txt\n", stderr="", returncode=0
            )
            res = agent._executer_everything("test", limit=None)

        self.assertEqual(res, ["C:\\a.txt", "C:\\b.txt"])
        # Ensure "-n 77" is passed
        called_cmd = sp_run.call_args[0][0]
        self.assertIn("-n", called_cmd)
        self.assertIn("77", called_cmd)

    def test_executer_everything_query_list_is_used_as_tokens(self):
        agent = self.make_agent()

        with patch("subprocess.run") as sp_run:
            sp_run.return_value = SimpleNamespace(stdout="X\n", stderr="", returncode=0)
            res = agent._executer_everything(['path:"C:\\tmp"', "foo"], limit=5)

        self.assertEqual(res, ["X"])
        called_cmd = sp_run.call_args[0][0]
        # Expect: [es.exe, -n, 5, ...tokens...]
        self.assertEqual(called_cmd[0], "es.exe")
        self.assertIn("foo", called_cmd)

    def test_executer_everything_fixes_path_token_ending_with_backslash_quote(self):
        agent = self.make_agent()

        bad = 'path:"C:\\X\\\\"'  # ends with \\" as literal characters
        with patch("subprocess.run") as sp_run:
            sp_run.return_value = SimpleNamespace(stdout="Y\n", stderr="", returncode=0)
            agent._executer_everything([bad], limit=5)

        called_cmd = sp_run.call_args[0][0]
        fixed_tokens = called_cmd[3:]
        token = fixed_tokens[0]
        self.assertTrue(token.endswith('"'))
        self.assertNotEqual(token[-2], "\\")

    def test_executer_everything_returncode_nonzero_returns_empty(self):
        agent = self.make_agent()
        with patch("subprocess.run") as sp_run:
            sp_run.return_value = SimpleNamespace(
                stdout="X\n", stderr="err", returncode=2
            )
            res = agent._executer_everything("test", limit=5)
        self.assertEqual(res, [])

    def test_executer_everything_empty_stdout_returns_empty(self):
        agent = self.make_agent()
        with patch("subprocess.run") as sp_run:
            sp_run.return_value = SimpleNamespace(stdout="", stderr="", returncode=0)
            res = agent._executer_everything("test", limit=5)
        self.assertEqual(res, [])


@unittest.skipIf(_skip_if_missing(), "Project imports not available.")
class TestReadmeTokenLogic(AgentRechercheUnitTestBase):
    def test_key_tokens_from_readme_parses(self):
        agent = self.make_agent()
        tokens = agent._key_tokens_from_readme("README_agent_contexte-faq.md")
        self.assertTrue({"agent", "contexte", "faq"}.issubset(tokens))

    def test_key_tokens_from_readme_invalid_name_raises(self):
        agent = self.make_agent()
        with self.assertRaises(RuntimeError):
            agent._key_tokens_from_readme("NOTREADME.md")


@unittest.skipIf(_skip_if_missing(), "Project imports not available.")
class TestTenterRecuperationResume(AgentRechercheUnitTestBase):
    def test_tenter_recuperation_resume_match_meta_message_turn(self):
        agent = self.make_agent()

        # Mock Everything returns 1 file
        agent._executer_everything = MagicMock(return_value=["C:\\persist\\x.json"])

        payload = {
            "session_id": "SID123",  # ✅ IMPORTANT
            "meta": {"message_turn": 12},
            "reponse": "resume ok",
        }
        with patch.object(Path, "read_text", return_value=json.dumps(payload)):
            res = agent._tenter_recuperation_resume("SID123", 12, "C:\\persist")
        self.assertIsNotNone(res)

        self.assertIsNotNone(res)
        self.assertEqual(res.type, "resume")
        self.assertIn("resume ok", res.contenu)

    def test_tenter_recuperation_resume_invalid_json_returns_none(self):
        agent = self.make_agent()
        agent._executer_everything = MagicMock(return_value=["C:\\persist\\bad.json"])

        with patch.object(Path, "read_text", return_value="{not json"):
            res = agent._tenter_recuperation_resume("SID123", 1, "C:\\persist")

        self.assertIsNone(res)


@unittest.skipIf(_skip_if_missing(), "Project imports not available.")
class TestRechercheContexteVectorielle(AgentRechercheUnitTestBase):
    def test_recherche_contexte_vectorielle_fail_fast_moteur_absent(self):
        agent = self.make_agent()
        agent.agent_memoire = SimpleNamespace(moteur_vectoriel=None)
        agent.auditor.get_path.return_value = "C:\\persist"

        with self.assertRaises(RuntimeError):
            agent.recherche_contexte_memoire_vectorielle("q", intention=None)

    def test_recherche_contexte_vectorielle_fail_fast_persistante_absente(self):
        agent = self.make_agent()
        agent.agent_memoire = SimpleNamespace(moteur_vectoriel=MagicMock())
        agent.auditor.get_path.return_value = None

        with self.assertRaises(RuntimeError):
            agent.recherche_contexte_memoire_vectorielle("q", intention=None)

    def test_recherche_contexte_vectorielle_boosting_applied(self):
        agent = self.make_agent()

        # moteur_vectoriel returns 3 items
        raw = [
            {
                "score": 1.0,
                "meta": {"contenu": "A", "fichier": "x.txt", "type": "vectoriel"},
            },
            {
                "score": 1.0,
                "meta": {"contenu": "B", "fichier": "y.txt", "type": "vectoriel"},
            },
            {
                "score": 1.0,
                "meta": {"contenu": "C", "fichier": "z.txt", "type": "vectoriel"},
            },
        ]
        moteur = SimpleNamespace(rechercher=MagicMock(return_value=raw))
        agent.agent_memoire = SimpleNamespace(moteur_vectoriel=moteur)
        agent.auditor.get_path.return_value = "C:\\persist"

        # Intention mock: must have .sujet/.action/.categorie with .value
        intention = SimpleNamespace(
            sujet=SimpleNamespace(value="Script"),
            action=SimpleNamespace(value="Coder"),
            categorie=SimpleNamespace(value="Analyser"),
        )

        # We craft titles to include terms: boosting looks at s.titre.lower()
        # title comes from Path(path_original).name; we control meta['fichier']
        raw[0]["meta"]["fichier"] = "SCRIPT_CODER_Analyser_x.json"
        raw[1]["meta"]["fichier"] = "random.json"
        raw[2]["meta"]["fichier"] = "SCRIPT_x.json"

        res = agent.recherche_contexte_memoire_vectorielle("q", intention=intention)
        self.assertIsInstance(res, ResultatRecherche)
        self.assertGreaterEqual(len(res.souvenirs_bruts), 1)

        # The boosted one (raw[0]) should be first
        self.assertIn("SCRIPT_CODER_ANALYSER", res.souvenirs_bruts[0].titre.upper())

    def test_recherche_contexte_vectorielle_swap_applied_for_historique(self):
        agent = self.make_agent()

        raw = [
            {
                "score": 1.0,
                "meta": {
                    "contenu": "ORIGINAL",
                    "fichier": "C:\\memoire\\historique\\interaction_1.json",
                    "type": "vectoriel",
                    "session_id": "SID",
                    "message_turn": 3,
                },
            }
        ]
        moteur = SimpleNamespace(rechercher=MagicMock(return_value=raw))
        agent.agent_memoire = SimpleNamespace(moteur_vectoriel=moteur)
        agent.auditor.get_path.return_value = "C:\\persist"

        # Force swap to return a summary souvenir
        agent._tenter_recuperation_resume = MagicMock(
            return_value=Souvenir(
                contenu="RESUME", titre="SCRIPT_CODER_x.json", type="resume", score=1.0
            )
        )

        res = agent.recherche_contexte_memoire_vectorielle("q", intention=None)
        self.assertEqual(res.souvenirs_bruts[0].contenu, "RESUME")
        self.assertEqual(res.souvenirs_bruts[0].type, "resume_consolide")


@unittest.skipIf(_skip_if_missing(), "Project imports not available.")
class TestRechercheHistorique(AgentRechercheUnitTestBase):
    def test_recherche_historique_calls_swapper_when_sid_turn_present(self):
        agent = self.make_agent()
        agent.auditor.get_path.return_value = "C:\\hist"

        # Mock files returned by glob
        fake_files = [
            Path("C:\\hist\\interaction_1.json"),
            Path("C:\\hist\\interaction_2.json"),
        ]

        # Patch Path.glob + os.path.getmtime
        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "glob", return_value=fake_files),
            patch("os.path.getmtime", return_value=1.0),
        ):
            # Each file read returns JSON with sid/turn
            agent._lire_fichier_safe = MagicMock(
                side_effect=[
                    json.dumps({"meta": {"session_id": "SID", "message_turn": 1}}),
                    json.dumps({"meta": {"session_id": "SID", "message_turn": 2}}),
                ]
            )
            agent._swapper_vers_resume = MagicMock(
                side_effect=[
                    Souvenir(contenu="S1", titre="R1.json", type="resume", score=1.0),
                    Souvenir(contenu="S2", titre="R2.json", type="resume", score=1.0),
                ]
            )

            res = agent.recherche_historique(limit=2)

        self.assertIsInstance(res, ResultatRecherche)
        self.assertEqual(agent._swapper_vers_resume.call_count, 2)


@unittest.skipIf(_skip_if_missing(), "Project imports not available.")
class TestRechercheVerbatim(AgentRechercheUnitTestBase):
    def test_recherche_interaction_verbatim_returns_proved_match(self):
        agent = self.make_agent()

        agent._recherche_whoosh_targeted = MagicMock(
            return_value=[
                Souvenir(
                    contenu="preview",
                    titre="interaction_123.json",
                    type="historique",
                    score=1.0,
                )
            ]
        )
        agent.auditor.get_path.return_value = "C:\\hist"

        # Make f_path.exists() true and read contain phrase
        with patch.object(Path, "exists", return_value=True):
            agent._lire_fichier_safe = MagicMock(
                return_value="hello EXACT_PHRASE world"
            )
            res = agent.recherche_interaction_verbatim("EXACT_PHRASE")

        self.assertIsInstance(res, ResultatRecherche)
        self.assertEqual(len(res.souvenirs_bruts), 1)
        self.assertEqual(res.souvenirs_bruts[0].type, "verbatim_prouve")


@unittest.skipIf(_skip_if_missing(), "Project imports not available.")
class TestRechercheFichierHorsMemoire(AgentRechercheUnitTestBase):
    def test_recherche_fichier_hors_memoire_filters_blacklist_and_whitelist(self):
        agent = self.make_agent()
        agent.auditor.recuperer_racine_projet.return_value = "C:\\proj"

        # Mix of candidates
        candidats = [
            "C:\\proj\\a.py",
            "C:\\proj\\b.yaml",
            "C:\\proj\\logs\\nope.py",
            "C:\\proj\\backups\\nope.yaml",
            "C:\\proj\\x - Copie.py",
            "C:\\proj\\y.bak",
            "C:\\proj\\z.txt",
            "C:\\proj\\.github\\workflows\\ci.yml",
        ]
        agent._executer_everything = MagicMock(return_value=candidats)
        agent._lire_fichier_safe = MagicMock(return_value="content")

        res = agent.recherche_fichier_hors_memoire("agent")

        titles = [s.titre for s in res.souvenirs_bruts]
        self.assertIn("a.py", titles)
        self.assertIn("b.yaml", titles)
        self.assertIn("ci.yml", titles)

        # Ensure blacklisted excluded
        self.assertNotIn("nope.py", titles)
        self.assertNotIn("nope.yaml", titles)
        self.assertNotIn("x - Copie.py", titles)
        self.assertNotIn("y.bak", titles)
        self.assertNotIn("z.txt", titles)


if __name__ == "__main__":
    unittest.main(verbosity=2)
