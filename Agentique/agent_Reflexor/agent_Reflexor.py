#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AgentReflexor - Moteur d'Introspection et d'Auto-Correction
Module responsable de la boucle de rétroaction (Feedback Loop) du système multi-agents.
Il implémente la capacité de métacognition permettant au système d'analyser ses propres erreurs,
d'en comprendre les causes et de générer dynamiquement de nouvelles règles de gouvernance.

Responsabilités principales :
    1. Analyse sémantique des incidents signalés (Trigger '!!!').
    2. Recherche vectorielle de précédents similaires (RAG sur erreurs passées).
    3. Classification structurée des écarts (Hallucination, Logique, Technique, etc.).
    4. Génération et injection à chaud de règles correctives (Self-Healing).
    5. Gestion du renforcement via feedback utilisateur (+1/-1).

Architectures impliquées :
    - Pipeline RAG inversé (Recherche d'erreurs similaires).
    - Chain-of-Thought (CoT) pour l'analyse causale.
    - Persistance dynamique (Création de règles JSON + Vectorisation immédiate).
"""

import json
import yaml
from datetime import datetime
from typing import Dict, List, Optional, TYPE_CHECKING
from pathlib import Path

from agentique.base.META_agent import AgentBase
from agentique.base.config_paths import ROOT_DIR
from agentique.base.contrats_interface import EntreeJournalReflexif, TypeEcart

# Import conditionnel
if TYPE_CHECKING:
    from agentique.sous_agents_gouvernes.agent_Memoire.agent_Memoire import AgentMemoire
    from agentique.sous_agents_gouvernes.agent_Parole.moteurs.moteur_llm import (
        MoteurLLM,
    )
    from agentique.sous_agents_gouvernes.agent_Memoire.moteur_vecteur import (
        MoteurVectoriel,
    )


class AgentReflexor(AgentBase):
    def __init__(
        self,
        agent_memoire: Optional["AgentMemoire"] = None,
        moteur_llm: Optional["MoteurLLM"] = None,
        moteur_vectoriel: Optional["MoteurVectoriel"] = None,
        *args,
        **kwargs,
    ):
        """
        Initialise avec agents injectés par Semi et charge la config YAML.
        """
        super().__init__(nom_agent="AgentReflexor")

        # 1. Chargement Configuration
        self.config_data = self._charger_config_yaml()
        self.conf_reflexor = self.config_data.get("configuration", {})

        # Mapping des configurations
        self.conf_analyse = self.conf_reflexor.get("analyse", {})
        self.conf_feedback = self.conf_reflexor.get("feedback", {})

        # 2. Vérification Dépendances
        if agent_memoire is None:
            raise RuntimeError("AgentMemoire est OBLIGATOIRE pour Reflexor")
        if moteur_llm is None:
            raise RuntimeError("MoteurLLM est OBLIGATOIRE pour Reflexor")

        self.agent_memoire = agent_memoire
        self.moteur_llm = moteur_llm
        self.moteur_vectoriel = moteur_vectoriel

        self.logger.info("✅ AgentReflexor initialisé (Config YAML chargée).")

    def _charger_config_yaml(self) -> Dict:
        """Charge le fichier config_reflexor.yaml local ou via ROOT_DIR."""
        path_conf = Path(__file__).parent / "config_reflexor.yaml"
        if not path_conf.exists():
            path_conf = (
                ROOT_DIR
                / "agentique"
                / "sous_agents_gouvernes"
                / "agent_Reflexor"
                / "config_reflexor.yaml"
            )

        if not path_conf.exists():
            raise RuntimeError("❌ Fichier 'config_reflexor.yaml' introuvable.")

        with open(path_conf, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def rechercher_cas_similaires(self, texte: str, top_k: int = None) -> List[Dict]:
        """
        Interroge la mémoire vectorielle pour identifier des précédents contextuels pertinents.

        Cette méthode permet d'enrichir le prompt d'analyse avec des exemples historiques (Few-Shot),
        augmentant ainsi la précision du diagnostic du LLM sur l'erreur actuelle.

        Args:
            texte (str): Le signalement ou le prompt ayant causé l'erreur.
            top_k (int, optional): Nombre de voisins à récupérer. Défaut via config.

        Returns:
            List[Dict]: Liste des métadonnées des incidents similaires trouvés.
        """
        if top_k is None:
            top_k = self.conf_analyse.get("top_k_similaires_default", 5)

        if self.moteur_vectoriel:
            resultats = self.moteur_vectoriel.rechercher(texte, top_k)
            self.logger.log_thought(f"🧩 {len(resultats)} cas similaires trouvés")
            return resultats
        return []

    def _analyser_incident_complet(
        self, prompt_erreur: str, historique: List[str], cas_similaires: List[Dict]
    ) -> Dict:
        """
        Exécute l'analyse cognitive de l'incident via le Moteur LLM.

        Construit un prompt complexe intégrant :
        1. L'historique récent de la conversation (Contexte immédiat).
        2. Les incidents similaires récupérés (Mémoire à long terme).
        3. Une directive stricte de formatage JSON.

        Args:
            prompt_erreur (str): Le signalement explicite de l'utilisateur.
            historique (List[str]): Les derniers échanges de la session.
            cas_similaires (List[Dict]): Contextes injectés via RAG.

        Returns:
            Dict: Structure JSON validée contenant le diagnostic (Type, Cause, Correction).
        """
        self.logger.info("🧠 Lancement de l'analyse structurelle de l'erreur...")

        # Utilisation de la config pour la fenêtre d'historique
        taille_window = self.conf_analyse.get("taille_historique_contexte", 6)
        historique_str = "\n".join(historique[-taille_window:])

        # Contexte mémoire pour aider le jugement
        contexte_memoire = ""
        if cas_similaires:
            contexte_memoire = "\n--- PRÉCÉDENTS SIMILAIRES ---\n"
            for i, cas in enumerate(cas_similaires[:2], 1):
                meta = cas.get("meta", {})
                contenu = meta.get("contenu", "N/A")
                contexte_memoire += f"Cas {i}:\n{contenu[:200]}...\n"

        prompt_analyse = f"""[ANALYSE RÉFLEXIVE SYSTÈME]
Tu es le module d'introspection de l'IA. Une erreur a été signalée par l'utilisateur (signal '!!!').
Ton but est de remplir une fiche d'incident précise au format JSON.

CONTEXTE :
---
{historique_str}
{contexte_memoire}
---
SIGNALEMENT UTILISATEUR : "{prompt_erreur}"
---

INSTRUCTIONS :
Analyse l'erreur et retourne un JSON strict avec ces clés :
1. "erreur_commise": Description factuelle courte de l'erreur (le fait brut).
2. "type_ecart": Choisir PARMI : "Hallucination", "Gouvernance", "Logique", "Biais", "Visuel", "Technique".
3. "regle_enfreinte": Quelle règle explicite ou implicite a été violée ? (Cite un fichier si possible).
4. "hypothese_causale": Pourquoi l'IA s'est trompée ? (Analyse métacognitive : pattern hérité, contexte ignoré, etc.).
5. "correction_immediate": Quelle action corrective ou règle immédiate faut-il appliquer ?

IMPORTANT :
- Sois clinique et précis.
- "hypothese_causale" doit expliquer le processus cognitif fautif.
- "correction_immediate" doit être une action concrète (ex: "Verrouillage règle X").

Réponds UNIQUEMENT avec le bloc JSON.
"""

        try:
            response_dict = self.moteur_llm.generer(prompt_text=prompt_analyse)

            # Extraction et parsing du JSON
            raw_text = response_dict.get("response", "").strip()
            # Nettoyage basique des balises markdown si présentes
            if "```json" in raw_text:
                raw_text = raw_text.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_text:
                raw_text = raw_text.split("```")[1].split("```")[0].strip()

            data = json.loads(raw_text)
            return data

        except Exception as e:
            self.logger.log_error(f"Échec analyse JSON: {e}")
            # Fallback en cas d'échec du parsing
            return {
                "erreur_commise": "Erreur d'analyse réflexive",
                "type_ecart": "Technique",
                "regle_enfreinte": "Non identifiée",
                "hypothese_causale": f"Échec du parsing JSON du LLM : {e}",
                "correction_immediate": "Audit des logs Reflexor requis.",
            }

    def lancer_analyse_gouvernance(self, prompt_erreur: str, historique: List[str]):
        """
        Orchestre le cycle complet de la boucle réflexive (Protocole ALERTE).

        Pipeline de traitement :
        1. Retrieval : Récupération du contexte et des précédents vecteurs.
        2. Cognition : Analyse LLM pour déterminer la cause racine et le type d'écart.
        3. Serialization : Création d'un objet 'EntreeJournalReflexif' validé.
        4. Persistence : Journalisation Markdown pour l'audit humain.
        5. Self-Correction : Génération automatique d'une règle (JSON), sauvegarde disque
           et vectorisation immédiate pour prise en compte au prochain tour.

        Args:
            prompt_erreur (str): Le trigger d'alerte (ex: "!!! Tu as oublié X").
            historique (List[str]): Contexte conversationnel pour l'analyse.
        """
        self.logger.info("🚨 Boucle Réflexive (!!!) démarrée.")

        # 1. Recherche de contexte (Paramètre Config)
        k_gouv = self.conf_analyse.get("top_k_gouvernance", 3)
        cas_similaires = self.rechercher_cas_similaires(prompt_erreur, top_k=k_gouv)

        # 2. Analyse structurelle par le LLM
        analyse_data = self._analyser_incident_complet(
            prompt_erreur, historique, cas_similaires
        )

        # 3. Mapping vers l'Enum TypeEcart
        type_str = analyse_data.get("type_ecart", "Technique")
        try:
            type_ecart_enum = TypeEcart(type_str)
        except ValueError:
            self.logger.log_warning(
                f"Type d'écart inconnu '{type_str}', fallback sur TECHNIQUE"
            )
            type_ecart_enum = TypeEcart.TECHNIQUE

        # 4. Création de l'objet Dataclass
        entree_reflexive = EntreeJournalReflexif(
            erreur_commise=analyse_data.get("erreur_commise", "Erreur inconnue"),
            type_ecart=type_ecart_enum,
            contexte=f"Signalement utilisateur via '!!!' sur prompt : {prompt_erreur[:50]}...",
            regle_enfreinte=analyse_data.get("regle_enfreinte", "Non spécifiée"),
            hypothese_causale=analyse_data.get("hypothese_causale", "Non identifiée"),
            correction_injectee=analyse_data.get("correction_immediate", "Aucune"),
        )

        # 🛡️👁️‍🗨️🛡️# VALIDATION FORMAT SORTIE
        self.auditor.valider_format_sortie(entree_reflexive)

        # 5. Génération Markdown
        trace_markdown = entree_reflexive.to_markdown()

        # 6. Journalisation via AgentMemoire (Trace MD)
        self.agent_memoire.journaliser_trace_reflexive(
            trace_markdown=trace_markdown,
            type_erreur=type_ecart_enum.value,
            classification="Gouvernance",
        )

        # =================================================================
        # 7. (AJOUT CRITIQUE) CRÉATION & SAUVEGARDE DE LA RÈGLE
        # =================================================================
        # A. On génère le texte de la règle via le LLM
        texte_regle = self.creer_regle_auto_correction(analyse_data)

        if texte_regle and "Erreur" not in texte_regle:
            # B. On prépare le nom du fichier
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            nom_fichier_regle = f"R_CORRECTION_{ts}.json"

            # C. Payload JSON
            payload_regle = {
                "regle": texte_regle,
                "meta": {
                    "source": "Reflexor_Auto",
                    "trigger": "Protocole_ALERTE",
                    "incident_lie": analyse_data.get("erreur_commise"),
                    "timestamp": datetime.now().isoformat(),
                },
            }

            # D. Sauvegarde physique via AgentMemoire
            succes_save = self.agent_memoire.sauvegarder_memoire(
                contenu=payload_regle,
                type_memoire="regles",
                nom_fichier=nom_fichier_regle,
            )

            if succes_save:
                self.logger.info(
                    f"✅ Règle de correction active créée et sauvegardée : {nom_fichier_regle}"
                )

                # ✅ AJOUT CRITIQUE V3 : Vectorisation immédiate dans le moteur DÉDIÉ
                self.agent_memoire.vectoriser_regle(
                    contenu_regle=texte_regle, metadata=payload_regle["meta"]
                )

                # E. Mise à jour Whoosh (Mots-clés) - On garde aussi pour la redondance
                if self.agent_memoire.agent_recherche:
                    self.agent_memoire.agent_recherche.update_index(
                        nouveau_fichier=str(
                            Path(self.auditor.get_path("regles")) / nom_fichier_regle
                        ),
                        type_memoire="regles",
                        categorie="correction_comportementale",
                    )
        # =================================================================

        self.logger.signal_gouvernance("✅ Entrée réflexive standardisée générée.")
        self.stats_manager.incrementer_stat_specifique("problemes_detectes")

    def creer_regle_auto_correction(self, cas_analyse: Dict) -> str:
        """Génère le contenu textuel d'une nouvelle règle de gouvernance basée sur le diagnostic.

        Transforme l'hypothèse causale (ex: "J'ai oublié le format") en une directive
        système impérative et actionnable (ex: "Toujours vérifier le format X avant de répondre").

        Args:
            cas_analyse (Dict): Le dictionnaire de résultats issu de _analyser_incident_complet.

        Returns:
            str: Le corps de la règle au format Markdown/Texte.
        """

        contexte_erreur = f"Erreur : {cas_analyse.get('erreur_commise')}"

        prompt_systeme = (
            "Vous êtes le moteur d'introspection. "
            "Analysez l'erreur ci-dessous et générez UNIQUEMENT une liste d'actions correctives concrètes (Markdown).\n"
            f"{contexte_erreur}\n"
            "Correction :"
        )

        try:
            response_dict = self.moteur_llm.generer(prompt_text=prompt_systeme)

            if "error" in response_dict:
                raise RuntimeError(response_dict["error"])

            correction = response_dict.get("response", "").strip()
            return correction if correction else "* [Erreur] Correction vide."

        except Exception as e:
            self.logger.log_error(f"Échec génération règle: {e}")
            return "* [Erreur Système] Impossible de générer la règle."

    # -------------------------------
    # ENREGISTREMENT FEEDBACK UTILISATEUR
    # -------------------------------

    def enregistrer_feedback_etendu(
        self, prompt: str, reponse: str, score: float, mot_cle: str = "général"
    ) -> bool:
        """
        Traite et persiste les signaux de renforcement (feedback) explicites de l'utilisateur.

        Gère la sauvegarde des métriques de performance et déclenche, si le score est positif
        et le tag pertinent, une réindexation prioritaire dans le moteur de recherche (Whoosh)
        pour renforcer les comportements validés.

        Args:
            prompt (str): La demande initiale.
            reponse (str): La réponse fournie par l'agent.
            score (float): Score de satisfaction (0.0 à 1.0).
            mot_cle (str): Tag contextuel (ex: "mémoire", "code", "style").

        Returns:
            bool: True si l'enregistrement et l'indexation ont réussi.
        """
        try:
            # Récupération Seuils Config
            seuil_positif = self.conf_feedback.get("seuil_positif", 0.5)
            trigger_word = self.conf_feedback.get("mot_cle_declencheur", "mémoire")

            # 1. Données
            feedback = {
                "timestamp": datetime.now().isoformat(),
                "prompt": prompt,
                "reponse": reponse,
                "score": score,
                "tag": mot_cle,
            }

            # 2. Sauvegarde
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            is_positive = score > seuil_positif
            prefixe = "+1" if is_positive else "-1"

            nom_fichier = f"feedback_{prefixe}_{mot_cle}_{timestamp_str}.json"

            succes = self.agent_memoire.sauvegarder_memoire(
                contenu=feedback,
                type_memoire="reflexive",
                nom_fichier=f"feedback/{nom_fichier}",
            )

            # 3. Action Spéciale : Réindexation si mémoire positive
            if succes and mot_cle == trigger_word and is_positive:
                path_complet = (
                    Path(self.auditor.get_path("reflexive")) / "feedback" / nom_fichier
                )

                if self.agent_memoire.agent_recherche:
                    self.agent_memoire.agent_recherche.update_index(
                        nouveau_fichier=str(path_complet),
                        type_memoire="reflexive",
                        sujet="Feedback",
                        action="Correction",
                        categorie="Mémoire",
                    )
                    self.logger.info("💾 Index Whoosh mis à jour (+1 mémoire).")

            self.stats_manager.incrementer_stat_specifique("analyses_effectuees")
            return succes

        except Exception as e:
            self.logger.log_error(f"Erreur enregistrement feedback : {e}")
            return False
