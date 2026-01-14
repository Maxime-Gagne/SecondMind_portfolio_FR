#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agent_Reflexor_UNITTEST.py
Unit tests (unittest + mocks) for AgentReflexor.

Strategy:
- Avoid calling AgentReflexor.__init__ (loads YAML, checks deps) by using __new__
  and injecting dependencies + config dicts directly.
- Mock all I/O, time, and external dependencies (LLM, Memoire, Vectoriel, Auditor).

Ref: agent_Reflexor.py :contentReference[oaicite:0]{index=0}
"""

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, mock_open

# ---- Project imports (adjust if needed) ----
try:
    # If tests are in same folder as agent_Reflexor.py:
    from agent_Reflexor import AgentReflexor
except Exception:
    AgentReflexor = None

try:
    from agentique.base.contrats_interface import EntreeJournalReflexif, TypeEcart
except Exception:
    EntreeJournalReflexif = None
    TypeEcart = None


def _skip_if_missing():
    return AgentReflexor is None or EntreeJournalReflexif is None or TypeEcart is None


class AgentReflexorUnitTestBase(unittest.TestCase):
    """Build AgentReflexor without __init__ and inject mocks."""

    def make_agent(self):
        if _skip_if_missing():
            self.skipTest(
                "Project imports not available (AgentReflexor / contrats_interface)."
            )

        agent = AgentReflexor.__new__(AgentReflexor)

        # Core dependencies
        agent.agent_memoire = MagicMock()
        agent.moteur_llm = MagicMock()
        agent.moteur_vectoriel = MagicMock()

        # Universal tools (from AgentBase) mocked
        agent.logger = MagicMock()
        agent.auditor = MagicMock()
        agent.stats_manager = MagicMock()

        # Config fragments used by methods
        agent.conf_analyse = {
            "top_k_similaires_default": 5,
            "taille_historique_contexte": 6,
            "top_k_gouvernance": 3,
        }
        agent.conf_feedback = {
            "seuil_positif": 0.5,
            "mot_cle_declencheur": "mémoire",
        }

        return agent


@unittest.skipIf(_skip_if_missing(), "Project imports not available.")
class TestRechercherCasSimilaires(AgentReflexorUnitTestBase):
    def test_top_k_none_uses_config_default(self):
        agent = self.make_agent()
        agent.conf_analyse["top_k_similaires_default"] = 9

        agent.moteur_vectoriel.rechercher.return_value = [{"meta": {"contenu": "x"}}]

        res = agent.rechercher_cas_similaires("hello", top_k=None)

        agent.moteur_vectoriel.rechercher.assert_called_once_with("hello", 9)
        self.assertEqual(res, [{"meta": {"contenu": "x"}}])

    def test_no_vector_engine_returns_empty(self):
        agent = self.make_agent()
        agent.moteur_vectoriel = None

        res = agent.rechercher_cas_similaires("hello", top_k=2)
        self.assertEqual(res, [])


@unittest.skipIf(_skip_if_missing(), "Project imports not available.")
class TestAnalyserIncidentComplet(AgentReflexorUnitTestBase):
    def test_parses_json_plain(self):
        agent = self.make_agent()

        llm_payload = {
            "response": json.dumps(
                {
                    "erreur_commise": "X",
                    "type_ecart": "Logique",
                    "regle_enfreinte": "R_001",
                    "hypothese_causale": "Y",
                    "correction_immediate": "Z",
                }
            )
        }
        agent.moteur_llm.generer.return_value = llm_payload

        res = agent._analyser_incident_complet(
            prompt_erreur="!!!", historique=["a", "b", "c"], cas_similaires=[]
        )

        self.assertEqual(res["type_ecart"], "Logique")
        self.assertEqual(res["regle_enfreinte"], "R_001")

    def test_parses_json_in_markdown_fence(self):
        agent = self.make_agent()

        agent.moteur_llm.generer.return_value = {
            "response": "```json\n" + json.dumps({"type_ecart": "Biais"}) + "\n```"
        }

        res = agent._analyser_incident_complet("!!!", ["x"], [])
        self.assertEqual(res["type_ecart"], "Biais")

    def test_fallback_when_json_invalid(self):
        agent = self.make_agent()
        agent.moteur_llm.generer.return_value = {"response": "not-json"}

        res = agent._analyser_incident_complet("!!!", ["x"], [])

        self.assertEqual(res["type_ecart"], "Technique")
        self.assertIn("Échec du parsing JSON", res["hypothese_causale"])


@unittest.skipIf(_skip_if_missing(), "Project imports not available.")
class TestCreerRegleAutoCorrection(AgentReflexorUnitTestBase):
    def test_returns_llm_text(self):
        agent = self.make_agent()
        agent.moteur_llm.generer.return_value = {"response": "- Action 1\n- Action 2"}

        out = agent.creer_regle_auto_correction({"erreur_commise": "oops"})
        self.assertIn("Action 1", out)

    def test_returns_error_when_llm_returns_error_key(self):
        agent = self.make_agent()
        agent.moteur_llm.generer.return_value = {"error": "boom"}

        out = agent.creer_regle_auto_correction({"erreur_commise": "oops"})
        self.assertIn("[Erreur Système]", out)

    def test_returns_error_when_llm_raises(self):
        agent = self.make_agent()
        agent.moteur_llm.generer.side_effect = RuntimeError("x")

        out = agent.creer_regle_auto_correction({"erreur_commise": "oops"})
        self.assertIn("[Erreur Système]", out)


@unittest.skipIf(_skip_if_missing(), "Project imports not available.")
class TestLancerAnalyseGouvernance(AgentReflexorUnitTestBase):
    @patch("agent_Reflexor.datetime")
    def test_pipeline_happy_path_creates_rule_and_vectorizes(self, dt):
        agent = self.make_agent()

        # Freeze time for deterministic filenames/metadata
        dt.now.return_value = SimpleNamespace(
            strftime=lambda fmt: "20260107_203000"
            if "%Y%m%d_%H%M%S" in fmt
            else "2026-01-07T20:30:00",
            isoformat=lambda: "2026-01-07T20:30:00",
        )

        # 1) Similar cases
        agent.rechercher_cas_similaires = MagicMock(
            return_value=[
                {"meta": {"contenu": "ancien incident A"}},
            ]
        )

        # 2) Analysis result (type_ecart valid)
        agent._analyser_incident_complet = MagicMock(
            return_value={
                "erreur_commise": "A oublié la config",
                "type_ecart": "Gouvernance",
                "regle_enfreinte": "config comme seule source de vérité",
                "hypothese_causale": "hardcode",
                "correction_immediate": "Toujours charger config depuis YAML",
            }
        )

        # 3) Rule generation
        agent.creer_regle_auto_correction = MagicMock(
            return_value="- Toujours lire le YAML"
        )

        # 4) Save ok
        agent.agent_memoire.sauvegarder_memoire.return_value = True
        agent.auditor.get_path.return_value = "C:\\regles"

        # 5) agent_recherche exists for update_index
        agent.agent_memoire.agent_recherche = MagicMock()

        # Act
        agent.lancer_analyse_gouvernance("!!! tu as hardcodé", ["u1", "a1", "u2", "a2"])

        # Assert: journalisation trace
        agent.agent_memoire.journaliser_trace_reflexive.assert_called_once()
        # Assert: sauvegarde règle + vectorisation
        agent.agent_memoire.sauvegarder_memoire.assert_called()
        agent.agent_memoire.vectoriser_regle.assert_called_once()
        # Assert: update_index called (redundant indexing)
        agent.agent_memoire.agent_recherche.update_index.assert_called_once()
        # Assert: stats increment
        agent.stats_manager.incrementer_stat_specifique.assert_called_with(
            "problemes_detectes"
        )

    def test_unknown_type_ecart_fallback_to_technique(self):
        agent = self.make_agent()

        agent.rechercher_cas_similaires = MagicMock(return_value=[])
        agent._analyser_incident_complet = MagicMock(
            return_value={
                "erreur_commise": "X",
                "type_ecart": "INCONNU_TOTAL",
                "regle_enfreinte": "N/A",
                "hypothese_causale": "N/A",
                "correction_immediate": "N/A",
            }
        )

        # Return "Erreur" so rule creation block is skipped
        agent.creer_regle_auto_correction = MagicMock(return_value="* [Erreur] ...")

        agent.lancer_analyse_gouvernance("!!!", ["a", "b"])
        # Should have logged warning about unknown type
        agent.logger.log_warning.assert_called()
        agent.agent_memoire.journaliser_trace_reflexive.assert_called_once()


@unittest.skipIf(_skip_if_missing(), "Project imports not available.")
class TestEnregistrerFeedbackEtendu(AgentReflexorUnitTestBase):
    @patch("agent_Reflexor.datetime")
    def test_saves_feedback_and_updates_index_when_positive_memory(self, dt):
        agent = self.make_agent()

        dt.now.return_value = SimpleNamespace(
            strftime=lambda fmt: "20260107_203000",
            isoformat=lambda: "2026-01-07T20:30:00",
        )

        agent.agent_memoire.sauvegarder_memoire.return_value = True
        agent.auditor.get_path.return_value = "C:\\memoire\\reflexive"

        agent.agent_memoire.agent_recherche = MagicMock()

        ok = agent.enregistrer_feedback_etendu(
            prompt="p", reponse="r", score=1.0, mot_cle="mémoire"
        )

        self.assertTrue(ok)
        agent.agent_memoire.sauvegarder_memoire.assert_called_once()
        agent.agent_memoire.agent_recherche.update_index.assert_called_once()
        agent.stats_manager.incrementer_stat_specifique.assert_called_with(
            "analyses_effectuees"
        )

    @patch("agent_Reflexor.datetime")
    def test_no_index_update_when_not_trigger_word(self, dt):
        agent = self.make_agent()

        dt.now.return_value = SimpleNamespace(
            strftime=lambda fmt: "20260107_203000",
            isoformat=lambda: "2026-01-07T20:30:00",
        )

        agent.agent_memoire.sauvegarder_memoire.return_value = True
        agent.auditor.get_path.return_value = "C:\\memoire\\reflexive"
        agent.agent_memoire.agent_recherche = MagicMock()

        ok = agent.enregistrer_feedback_etendu(
            prompt="p",
            reponse="r",
            score=1.0,
            mot_cle="style",  # not trigger
        )

        self.assertTrue(ok)
        agent.agent_memoire.agent_recherche.update_index.assert_not_called()

    def test_returns_false_on_exception(self):
        agent = self.make_agent()
        agent.agent_memoire.sauvegarder_memoire.side_effect = RuntimeError("disk error")

        ok = agent.enregistrer_feedback_etendu("p", "r", 1.0, "mémoire")
        self.assertFalse(ok)
        agent.logger.log_error.assert_called()


@unittest.skipIf(_skip_if_missing(), "Project imports not available.")
class TestChargerConfigYaml(unittest.TestCase):
    def test_charger_config_yaml_reads_local_file_first(self):
        agent = AgentReflexor.__new__(AgentReflexor)

        fake_yaml = "configuration:\n  analyse:\n    top_k_similaires_default: 7\n"

        with (
            patch.object(Path, "exists", return_value=True),
            patch("builtins.open", mock_open(read_data=fake_yaml)),
        ):
            out = AgentReflexor._charger_config_yaml(agent)

        self.assertIn("configuration", out)
        self.assertEqual(out["configuration"]["analyse"]["top_k_similaires_default"], 7)


if __name__ == "__main__":
    unittest.main(verbosity=2)
