#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# pylint: disable=method-hidden
# pylint: disable=no-member
"""
AgentSemi - Orchestrateur Central et Gestionnaire de Flux (Runtime)
Module principal qui initialise le système, maintient l'état de la session et pilote la boucle de pensée.

Architecture :
    - Pattern : Orchestrateur centralisé (Hub & Spoke).
    - Exécution : Synchrone pour la génération, Asynchrone (Threading) pour la persistance et l'analyse.
    - I/O : Streaming via Generator (yield) pour une latence faible en frontend.

Responsabilités Techniques :
    1. **Initialization** : Injection de dépendances et ordre de chargement critique des sous-agents.
    2. **Cognitive Loop** : Pipeline Intention -> RAG -> Prompting -> Inférence -> Outils.
    3. **Tool Routing** : Parsing des sorties JSON du LLM et dispatch vers les fonctions internes.
    4. **Background Tasks** : Délégation des I/O lourds (sauvegarde, indexation code) à des threads démons.
"""

import json
import re
import time
import requests
from scipy import stats
import yaml
import uuid
from datetime import datetime
from dataclasses import asdict, is_dataclass
import threading
from typing import List, Dict, Optional, Any, Callable, TYPE_CHECKING
from pathlib import Path

if TYPE_CHECKING:
    from flask_socketio import SocketIO  # Pour que VS Code comprenne le type
from agentique.base.META_agent import AgentBase
from agentique.base.contrats_interface import (
    Action,
    Categorie,
    StatsBase,
    Sujet,
    SearchMode,
    Interaction,
    MetadataFichier,
    MetadataPipeline,
    ResultatIntention,
    ResultatRecherche,
    ResultatContexte,
    ResultatJuge,
    StandardPrompt,
    StandardPromptCode,
    WebSearchPrompt,
    ProtocolePrompt,
    ManualContextCodePrompt,
    MemorySearchPrompt,
    CartographyPrompt,
    FileInspectionPrompt,
    StagingReviewPrompt,
    ModificateursCognitifs,
    Souvenir,
    CodeChunk,
    CustomJSONEncoder,
    PlanExecution,
    MemorySearchFirstPrompt,
)

from agentique.sous_agents_gouvernes.agent_Memoire.agent_Memoire import AgentMemoire
from agentique.sous_agents_gouvernes.agent_Parole.agent_Parole import AgentParole
from agentique.sous_agents_gouvernes.agent_Parole.moteurs.moteur_llm import MoteurLLM
from agentique.sous_agents_gouvernes.agent_Parole.moteurs.moteur_mini_llm import (
    MoteurMiniLLM,
)
from agentique.sous_agents_gouvernes.agent_Juge.agent_Juge import AgentJuge
from agentique.sous_agents_gouvernes.agent_Reflexor.agent_Reflexor import AgentReflexor
from agentique.sous_agents_gouvernes.agent_Recherche.agent_Recherche import (
    AgentRecherche,
)
from agentique.sous_agents_gouvernes.agent_Contexte.agent_Contexte import AgentContexte
from agentique.sous_agents_gouvernes.agent_Code.agent_Code import AgentCode
from agentique.sous_agents_gouvernes.agent_Code.code_extractor_manager import (
    CodeExtractorManager,
)
from agentique.Semi.classes_cognitives import IntentionDetector
from agentique.sous_agents_gouvernes.agent_Memoire.traitement_brute_persistante import (
    ProcesseurBrutePersistante,
)
from agentique.sous_agents_gouvernes.agent_Memoire.moteur_vecteur import MoteurVectoriel


class AgentSemi(AgentBase):
    def __init__(self, get_cache=None, get_lock=None, socketio=None):
        super().__init__(nom_agent="AgentSemi")

        """
        Contrôleur principal du runtime SecondMind.

        Gère le cycle de vie complet d'une requête utilisateur. Maintient les objets
        transverses (Cache, Lock, SocketIO) et assure la cohérence des données entre
        les différents moteurs (LLM, Vectoriel, Recherche).

        Attributes:
            current_session_id (str): UUID de la session active (pour le suivi conversationnel).
            active_plan (PlanExecution): État courant du plan d'action (passé de prompt en prompt).
            fichiers_actifs (Set[str]): Liste des fichiers "épinglés" dans le contexte courant (Working Set).
        """
        # ------------------------------------------------------
        # Dépendances (Cache / Monitoring)
        # ------------------------------------------------------
        self.socketio = socketio
        self.get_cache = get_cache
        self.get_lock = get_lock

        # 2. Initialisation des composants (Méthodes extraites)
        self._initialiser_moteurs()
        self._initialiser_sous_agents()
        self._initialiser_outils_systeme()
        self._initialiser_agent_code()

        # 3. Configuration Callback & État
        self._setup_callbacks_viewer()
        self._initialiser_etat_session()

        # 4. Démarrage des processus de fond
        self._lancer_processus_demarrage()

        self.logger.info("✅ AgentSemi initialisé (Refactorisé).")

    def _initialiser_outils_systeme(self):
        # On instancie le nouveau Manager (Outil stateless)
        self.code_extractor = CodeExtractorManager()

        # ------------------------------------------------------
        # Initialisation des Moteurs
        # ------------------------------------------------------

    def _initialiser_moteurs(self):
        self.moteur_llm = MoteurLLM()
        self.moteur_mini_llm = MoteurMiniLLM()
        self.moteur_vectoriel = MoteurVectoriel()
        self.processeur_batch = ProcesseurBrutePersistante(llm_engine=self.moteur_llm)

        # =====================================================
        # Initialisation des Agents (Ordre Strict)
        # =====================================================

    def _initialiser_sous_agents(self):
        """
        Instancie les agents et injecte les dépendances croisées.

        ⚠️ ORDRE CRITIQUE :
        1. Recherche (Base I/O)
        2. Memoire (Dépend de Recherche + Moteurs)
        3. Reflexor/Juge (Dépendent de Memoire/Recherche)
        4. Parole (Dépend de tout le monde pour construire le prompt)

        Modifie l'état interne de l'instance (self.agent_*).
        """
        self.agent_recherche = AgentRecherche()
        self.agent_recherche.moteur_vectoriel = self.moteur_vectoriel  # Injection

        self.agent_memoire: AgentMemoire = AgentMemoire(
            agent_recherche=self.agent_recherche, moteur_vectoriel=self.moteur_vectoriel
        )
        self.agent_recherche.agent_memoire = self.agent_memoire

        self.agent_reflexor = AgentReflexor(
            agent_memoire=self.agent_memoire,
            agent_recherche=self.agent_recherche,
            moteur_llm=self.moteur_llm,
            moteur_vectoriel=self.moteur_vectoriel,
        )
        self.agent_juge = AgentJuge(
            agent_recherche=self.agent_recherche, moteur_mini_llm=self.moteur_mini_llm
        )
        self.agent_contexte = AgentContexte(
            agent_recherche=self.agent_recherche, agent_juge=self.agent_juge
        )
        self.agent_parole: AgentParole = AgentParole(
            agent_contexte=self.agent_contexte,
            agent_semi=self,
            get_cache=self.get_cache,
            get_lock=self.get_lock,
        )

        self.intention_detector = IntentionDetector()

        # --- H. INJECTION TARDIVE POUR DEEP RESEARCH ---
        # AgentRecherche a besoin du LLM pour l'outil avancé, mais il a été créé avant.
        # On initialise l'outil maintenant que le moteur est dispo.
        from agentique.sous_agents_gouvernes.agent_Recherche.recherche_web import (
            RechercheWeb,
        )

        self.agent_recherche.outil_web = RechercheWeb(self.moteur_llm)
        self.logger.info("✅ Outil RechercheWeb injecté.")

    def _initialiser_agent_code(self):
        """Initialise le cerveau du code."""
        try:
            self.agent_code = AgentCode()  # ✅ Nouvelle classe
            self.logger.info("✅ AgentCode connecté.")
        except Exception as e:
            self.logger.log_error(f"⚠️ Échec init AgentCode: {e}")
            self.agent_code = None

        # =================================================================
        # 🔧 CORRECTIF PROMPT VIEWER : UNIVERSEL & SOCKET.IO
        # =================================================================

    def _setup_callbacks_viewer(self):
        """Configure le callback pour le Prompt Viewer (SocketIO)."""

        def update_viewer_callback(prompt_str):
            full_raw_prompt = (
                prompt_str if isinstance(prompt_str, str) else "Format Invalide"
            )

            cache = self.get_cache()
            lock = self.get_lock()

            with lock:
                cache["raw_prompt"] = full_raw_prompt
                cache["timestamp"] = datetime.now().isoformat()

            if self.socketio:
                try:
                    self.socketio.emit(
                        "refresh_prompt_viewer",
                        {"timestamp": datetime.now().isoformat(), "status": "updated"},
                    )
                except Exception as e:
                    print(f"⚠️ Erreur émission SocketIO: {e}")

        self.agent_parole._prompt_callback = update_viewer_callback

    def _initialiser_etat_session(self):
        """Initialise les variables d'état de session."""
        self.current_session_id = str(uuid.uuid4())
        self.current_message_turn = 0
        self.derniere_classification: Optional[ResultatIntention] = None
        self.derniere_interaction = None
        self.dernier_code_hash = None
        self.system_instructions = self.agent_parole.recuperer_instruction(
            "instructions_systeme"
        )
        self.active_plan = PlanExecution(objectif_global="")  # Utilise la dataclass
        # NOUVEAU : La liste des fichiers "ouverts" dans l'IDE mental de Semi
        self.fichiers_actifs = set()

    def _lancer_processus_demarrage(self):
        """
        Boot Sequence : Procédures de démarrage à froid.

        1. **Continuité** : Recharge les 10 derniers messages pour le contexte immédiat.
        2. **Maintenance** : Vérifie si un batch de vectorisation est en retard (ProcesseurBrutePersistante).
        3. **Identité** : Vérifie/Génère le résumé système initial.
        """

        # 1. Continuité de Session (Gouvernance)
        try:
            dernier_historique_chat = self.agent_contexte.get_historique_nouveau_chat()
            if dernier_historique_chat:
                self.agent_contexte.historique_conversation = dernier_historique_chat
                self.logger.info(
                    f"✅ Continuité établie: {len(dernier_historique_chat) // 2} échanges chargés."
                )
        except Exception as e:
            self.logger.log_error(f"Erreur chargement continuité: {e}")

        # 2. Vérification Batch Vectorisation
        self._verifier_batch_au_demarrage()

        # 3. Proprioception (Résumé Système)
        try:
            dossier_semi = Path(self.auditor.get_path("agent_dir"))
            resume_path = dossier_semi / "etat_systeme_resume.md"

            if not resume_path.exists():
                self.logger.info(
                    "🌱 Premier lancement : Génération de l'identité système..."
                )
                threading.Thread(
                    target=self.actualiser_resume_systeme, daemon=True
                ).start()
        except Exception as e:
            self.logger.log_warning(
                f"Impossible de vérifier le résumé système au démarrage : {e}"
            )

    # =========================================================================
    # 🕵️‍♂️ TRACEUR D'INVESTIGATION (NOUVEAU)
    # =========================================================================
    def _tracer_etape_investigation(
        self, etape: str, prompt_interne: str, reponse_llm: str, outil_resultat: dict
    ):
        """
        Enregistre les étapes intermédiaires de la boucle de recherche.
        Ne pollue pas la mémoire, c'est du log pur pour le débogage humain.
        """
        # On crée un fichier de log dédié par jour
        date_str = datetime.now().strftime("%Y-%m-%d")
        nom_log = f"trace_investigation_{date_str}.md"

        # On récupère le chemin des logs via l'auditor
        dossier_logs = self.auditor.get_path("logs")
        if not dossier_logs:
            return  # Si pas de logs configurés, on sort

        chemin_log = Path(dossier_logs) / nom_log
        timestamp = datetime.now().strftime("%H:%M:%S")

        # Extraction du raisonnement (souvent dans le JSON de réponse LLM)
        raisonnement = reponse_llm
        try:
            # Tentative d'extraction propre si c'est du JSON
            if "{" in reponse_llm:
                # On cherche le bloc JSON
                json_part = reponse_llm[
                    reponse_llm.find("{") : reponse_llm.rfind("}") + 1
                ]
                data = json.loads(json_part)
                # On cherche les clés standards de raisonnement
                raisonnement = (
                    data.get("analyse")
                    or data.get("thought")
                    or data.get("reasoning")
                    or reponse_llm
                )
        except:
            pass  # Si ça fail, on garde le texte brut

        bloc_log = (
            f"\n## 🕵️‍♂️ Étape : {etape} ({timestamp})\n"
            f"**🧠 Raisonnement :**\n> {str(raisonnement)[:1000]}\n\n"
            f"**📤 Prompt Interne (Envoyé au LLM) :**\n```text\n{prompt_interne[:2000]} ... [Tronqué]\n```\n\n"
            f"**📥 Résultat Outil (Reçu) :**\n```json\n{json.dumps(outil_resultat, ensure_ascii=False, indent=2)[:2000]} ... [Tronqué]\n```\n"
            f"---\n"
        )

        try:
            with open(chemin_log, "a", encoding="utf-8") as f:
                f.write(bloc_log)
        except Exception as e:
            self.logger.log_warning(f"⚠️ Impossible de tracer l'investigation : {e}")

        # ------------------------------------------------------
        # Méthode Principale de Pensée
        # ------------------------------------------------------

    def penser(
        self,
        prompt: str,
        interaction_id: str = None,  # <-- Optionnel (Généré si None)
        session_id: str = None,  # <-- Optionnel (Prend self.current... si None)
        message_turn: int = None,  # <-- Optionnel
        stream: bool = False,
        search_mode: str = "auto",
        historique_brut: Optional[List[str]] = None,
        enable_thinking: bool = False,
        archive_history: Optional[List[dict]] = None,
    ):
        """
        Boucle principale d'inférence (Main Loop).

        Pipeline d'exécution :
        1. **Pre-Flight** : Vérification des commandes système (ex: "+1", "!!!", "nouveau chat").
        2. **Routing** : Détection d'intention (Sujet/Action) via Regex ou LLM léger.
        3. **Retrieval** : Collecte du contexte (RAG standard + RAG Code + Recherche Web forcée).
        4. **Prompting** : Construction dynamique du prompt via AgentParole.
        5. **Inference** : Streaming de la réponse du LLM.
        6. **Tool Use** : Si du JSON est détecté, interruption du stream, exécution de l'outil, et récursion.
        7. **Post-Processing** : Lancement du thread asynchrone de sauvegarde.

        Args:
            prompt (str): Input utilisateur brut.
            stream (bool): Si True, yield les tokens en temps réel via SocketIO/HTTP.

        Yields:
            str: Tokens de texte ou signaux de contrôle.
        """

        # --- ⏱️ DÉBUT MOUCHARD ---
        t_start = time.time()
        logs_perf = []

        def tick(label):
            logs_perf.append(f"{label}: {time.time() - t_start:.2f}s")

        # -------------------------

        # --- GESTION DES ID & CONTINUITÉ ---
        if interaction_id is None:
            interaction_id = str(uuid.uuid4())

        # ✅ CORRECTION : Si pas d'ID reçu de l'interface, on utilise la session interne de Semi.
        # C'est ce qui assure la continuité de la mémoire vive.
        if session_id is None:
            session_id = self.current_session_id

        # On garde le compteur de tours synchronisé
        if message_turn is None:
            message_turn = self.current_message_turn

        # (On a SUPPRIMÉ le bloc "is_stateless" qui vidait 'historique_brut = []')

        # --- CHARGEMENT HISTORIQUE ARCHIVÉ ---
        if archive_history:
            historique_plat = [msg["content"] for msg in archive_history]
            self.agent_contexte.historique_conversation = historique_plat
            self.logger.info(
                f"📂 Historique archivé chargé: {len(archive_history) // 2} échanges"
            )
        # -------------------------------------

        correlation_id = self.logger.set_correlation_id()
        self.logger.info(f"Nouvelle requête [{correlation_id}] : {prompt[:50]}...")

        # Métriques Log (Volatiles)
        meta_pipeline = MetadataPipeline(interaction_id=str(uuid.uuid4()))

        print("DEBUG: 1. Penser démarré")
        # ==========================================================
        # 1. Gestion des Commandes Rapides (+1, -1, Piste Rapide)
        # ==========================================================
        resultat_commande = self._gerer_commandes_systeme(prompt, stream)

        print("DEBUG: 2. Commandes passées")
        # ------------------------------------------------------
        # --- NOUVEAU CHAT (premier message) -------------------
        # ------------------------------------------------------
        if resultat_commande == "NOUVEAU_CHAT":
            prompt_texte = self.agent_parole.prompt_premier_chat(prompt)

            # Génération directe
            response = ""
            for part in self.moteur_llm.generer_stream(prompt_texte):
                response += part
                if stream:
                    yield part

            self.agent_contexte.mettre_a_jour_historique(prompt, response)
            if not stream:
                yield response
            return
        print("DEBUG: 2.1 Commande nouveau chat passé")
        # Autres commandes (Feedback, etc.)
        if resultat_commande:
            if "yield" in resultat_commande:
                yield from resultat_commande["yield"]
                return
            elif "response" in resultat_commande:
                yield resultat_commande["response"]
                return
        print("DEBUG: 2.2 Autres commandes passées")
        # ------------------------------------------------------
        # 2. Gestion des Pistes Forcées (Web, Mémoire)
        # ------------------------------------------------------
        # ✅ CORRECTION : On vérifie explicitement le mode AVANT d'appeler le générateur
        if search_mode == "web":
            self.logger.info(f"🚀 Mode Recherche Web Forcée activé.")
            # On consomme le générateur
            for item in self._handle_forced_search(prompt, search_mode):
                yield item
            # On arrête le processus ici car c'est une demande spécifique
            return
        print("DEBUG: 3.0 Handled Forced Search Passé")
        # ==========================================================
        # 3. DÉTECTION D'INTENTION (Le Router)
        # ==========================================================
        # On le fait MAINTENANT pour savoir si on a besoin de l'enquêteur
        tick("Avant Intention")
        resultat_intention = self.intention_detector.intention_detector(
            prompt, historique_brut=historique_brut
        )
        tick("Après Intention")

        print(f"DEBUG: 3. Intention détectée: {resultat_intention.sujet}")
        # ------------------------------------------------------
        # 4. Préparation du Pipeline Principal (RAG)
        # ------------------------------------------------------
        mode_enum = SearchMode.NONE
        if search_mode == "web":
            mode_enum = SearchMode.WEB
        elif search_mode == "manual_context":
            mode_enum = SearchMode.CONTEXTE_MANUEL

        modificateurs = ModificateursCognitifs(
            activer_cot=False, enable_thinking=enable_thinking, search_mode=mode_enum
        )
        # ------------------------------------------------------
        # 5. RECHERCHE & CONTEXTE (Avec l'intention déjà calculée)
        # ------------------------------------------------------
        resultat_recherche = (
            self.agent_recherche.recherche_contexte_memoire_vectorielle(
                query=prompt, intention=resultat_intention
            )
        )
        tick("Après Recherche Vectorielle+Boost")

        # NOTE : Si AgentContexte ne gère pas les règles, il faudrait les appeler ici.
        # Mais supposons que AgentContexte fait son travail d'agrégation.

        resultat_contexte = self.agent_contexte.recuperer_contexte_intelligent(
            resultat_intention=resultat_intention, resultat_recherche=resultat_recherche
        )
        tick("Après Tri Contexte")

        # 🔴 Injection du PROTOCOLE ALERTE si actif
        if getattr(self, "active_protocol_override", None):
            protocole_souv = Souvenir(
                contenu=self.active_protocol_override,
                titre="PROTOCOLE_ALERTE",
                type="regle",
                score=999.0,
            )
            resultat_contexte.regles_actives.insert(0, protocole_souv)

        print("DEBUG: 5. Recherche finie")
        # ------------------------------------------------------
        # 6. RAG CODE (Canal Dédié)
        # ------------------------------------------------------
        liste_code_chunks: List[CodeChunk] = []  # Typage strict

        # Regex simplifiée pour déclenchement
        import re

        trigger_code = False
        if self.agent_code:
            # On cherche des indices de fichiers ou de structure technique
            if re.search(r"([a-zA-Z0-9_]+)\.(py|md|yaml|json)", prompt) or re.search(
                r"(code|fonction|classe|script|bug|erreur)", prompt, re.IGNORECASE
            ):
                # Appel à l'AgentCode
                raw_results = self.agent_code.fournir_contexte(prompt)

                # Conversion des résultats bruts en CodeChunk typés
                if raw_results:
                    trigger_code = True
                    for item in raw_results:
                        # 1. Extraction Contenu Robuste
                        contenu = ""
                        if hasattr(item, "contenu"):
                            contenu = item.contenu
                        elif hasattr(item, "code_summary"):
                            contenu = item.code_summary

                        # --- ✅ AJOUT : PASS-THROUGH DES ERREURS ---
                        # Si c'est une erreur technique, on bypass le filtre de longueur
                        is_error = getattr(item, "type", "") == "erreur_technique"

                        # FILTRE : Si le contenu est vide ou < 10 caractères (sauf si erreur), on jette
                        if not is_error and (not contenu or len(contenu.strip()) < 10):
                            continue

                        # 2. Extraction Nom (Gestion du Squelette/Souvenir)
                        # Souvenir utilise 'titre', ContexteCode utilise 'name'
                        nom_fichier = "Inconnu"
                        if hasattr(item, "titre"):
                            nom_fichier = item.titre
                        elif hasattr(item, "name"):
                            nom_fichier = item.name
                        elif hasattr(item, "chemin"):
                            nom_fichier = item.chemin

                        liste_code_chunks.append(
                            CodeChunk(
                                contenu=contenu,
                                chemin=nom_fichier,  # Maintenant le nom sera correct (ex: SQUELETTE_DYNAMIQUE)
                                type=getattr(item, "type", "snippet"),
                                langage="python",
                            )
                        )

        # ------------------------------------------------------
        # 6-BIS. INJECTION FICHIERS ACTIFS (Continuité Session)
        # ------------------------------------------------------
        # On ajoute les fichiers "épinglés" par les tours précédents pour éviter l'amnésie
        chunks_actifs = []
        fichiers_a_charger = getattr(self, "fichiers_actifs", [])

        if fichiers_a_charger:
            self.logger.info(f"📂 Injection contexte actif : {fichiers_a_charger}")

            # On vérifie la présence de l'outil de lecture
            outil = getattr(self.agent_recherche, "outil_recherche_memoire", None)

            if outil:
                for fichier in fichiers_a_charger:
                    try:
                        # Lecture via la méthode unifiée (celle utilisée par rechercher_memoire)
                        content = outil.lire_fichier_complet(fichier)

                        if content:
                            # Création du Chunk avec typage conforme pour AgentParole
                            chunks_actifs.append(
                                CodeChunk(
                                    contenu=content,
                                    chemin=fichier,
                                    type="fichier_actif",  # Permet à Parole d'appliquer le formatage spécial
                                    langage="python",
                                )
                            )
                    except Exception as e:
                        self.logger.log_warning(
                            f"⚠️ Impossible de relire le fichier actif {fichier}: {e}"
                        )
            else:
                self.logger.log_error(
                    "❌ outil_recherche_memoire non disponible pour l'injection active."
                )

        # ------------------------------------------------------
        # ✅ 7. CRÉATION DU PROMPT (MAPPING STRICT)
        # ==========================================================

        prompt_final_obj = None

        # --- A. MODE MANUEL (Priorité Absolue) ---
        if modificateurs.search_mode == SearchMode.CONTEXTE_MANUEL:
            self.logger.info("🚨 MODE INJECTION CODE MANUEL ACTIVÉ.")
            slots_list = (
                historique_brut
                if isinstance(historique_brut, list)
                else [str(historique_brut)]
            )
            code_joint = (
                "\n\n".join(slots_list).strip() if slots_list else "# Aucun code fourni"
            )

            prompt_final_obj = ManualContextCodePrompt(
                prompt_original=prompt,
                instructions_contexte_manuel=self.agent_parole.recuperer_instruction(
                    "instructions_contexte_manuel"
                ),
                contexte_manuel=code_joint,
                intention=resultat_intention,
                historique=resultat_contexte.historique,
                regles=resultat_contexte.regles_actives,
                fichiers_readme=resultat_contexte.fichiers_readme,
                modificateurs=modificateurs,
            )

        # --- B. MODE CARTOGRAPHIE (Nouveau) ---
        elif next(
            (
                s
                for s in resultat_contexte.contexte_memoire
                if s.type == "cartographie_projet"
            ),
            None,
        ):
            self.logger.info("🗺️ MODE DÉTECTÉ : CARTOGRAPHIE")
            souvenir_map = next(
                (
                    s
                    for s in resultat_contexte.contexte_memoire
                    if s.type == "cartographie_projet"
                ),
                None,
            )
            resume = self.agent_parole._recuperer_resume_systeme()

            prompt_final_obj = CartographyPrompt(
                prompt_original=prompt,
                instructions_cartographie=self.config.get("prompts", {}).get(
                    "instructions_cartographie", ""
                ),
                cartographie_projet=souvenir_map.contenu,
                plan_de_bataille=[resume],
                intention=resultat_intention,
            )

        # --- C. MODE INSPECTION FICHIER (Nouveau) ---
        # Si on a un fichier technique chargé ET qu'on veut analyser/coder
        elif next(
            (
                s
                for s in resultat_contexte.contexte_memoire
                if s.type in ["fichier_technique", "fichier_brut"]
            ),
            None,
        ) and resultat_intention.categorie in [
            Categorie.ANALYSER,
            Categorie.CODER,
            Categorie.AGENT,
        ]:
            souvenir_fichier = next(
                (
                    s
                    for s in resultat_contexte.contexte_memoire
                    if s.type in ["fichier_technique", "fichier_brut"]
                ),
                None,
            )
            self.logger.info(f"🔧 MODE DÉTECTÉ : INSPECTION ({souvenir_fichier.titre})")
            resume = self.agent_parole._recuperer_resume_systeme()

            prompt_final_obj = FileInspectionPrompt(
                prompt_original=prompt,
                instructions_inspection=self.config.get("prompts", {}).get(
                    "instructions_inspection", ""
                ),
                fichier_en_cours=souvenir_fichier,
                notes_precedentes=resume,
                intention=resultat_intention,
            )

        # --- D. MODE REVIEW (Nouveau) ---
        elif (
            resultat_intention.categorie == Categorie.PLANIFIER
            and "staging" in prompt.lower()
        ):
            self.logger.info("✅ MODE DÉTECTÉ : STAGING REVIEW")
            resume = self.agent_parole._recuperer_resume_systeme()
            prompt_final_obj = StagingReviewPrompt(
                prompt_original=prompt,
                instructions_review=self.config.get("prompts", {}).get(
                    "instructions_review", ""
                ),
                etat_staging_actuel=resume,
                derniere_action="Vérification demandée",
                intention=resultat_intention,
            )

        # --- E. MODE CODE STANDARD ---
        elif (trigger_code and liste_code_chunks) or chunks_actifs:
            self.logger.info(
                f"💻 MODE CODE ACTIVÉ : {len(liste_code_chunks)} RAG + {len(chunks_actifs)} Actifs."
            )
            prompt_final_obj = StandardPromptCode(
                prompt_original=prompt,
                instructions_code_prompt=self.agent_parole.recuperer_instruction(
                    "instructions_code_prompt"
                )
                or "Tu es un expert Python.",
                modificateurs=modificateurs,
                intention=resultat_intention,
                historique=resultat_contexte.historique,
                regles=resultat_contexte.regles_actives,
                fichiers_readme=resultat_contexte.fichiers_readme,
                code_chunks=liste_code_chunks + chunks_actifs,
            )

        # --- F. MODE STANDARD (Défaut) ---
        else:
            prompt_final_obj = StandardPrompt(
                prompt_original=prompt,
                instructions_systeme=self.agent_parole.recuperer_instruction(
                    "instructions_systeme"
                ),
                modificateurs=modificateurs,
                intention=resultat_intention,
                historique=resultat_contexte.historique,
                contexte_memoire=resultat_contexte.contexte_memoire,
                regles=resultat_contexte.regles_actives,
                fichiers_readme=resultat_contexte.fichiers_readme,
            )

        tick("7. Prompt Construit")
        self.derniere_classification = prompt_final_obj.intention
        # ------------------------------------------------------
        # 8. Génération (Appel AgentParole -> LLM)
        # ==========================================================
        final_response_text = ""
        llm_success = True
        prompt_texte = self.agent_parole.construire_prompt_llm(prompt_final_obj)
        tick("8. Envoi au Moteur LLM...")

        t_gen_start = time.time()
        first_token_received = False
        buffer_detection = ""
        check_json_done = False
        is_hidden_json_mode = False

        response_generator = self.moteur_llm.generer_stream(prompt_texte)

        try:
            for token in response_generator:
                if not token:
                    continue
                if not first_token_received:
                    ttft = time.time() - t_gen_start
                    tick(f"⚡ TTFT: {ttft:.2f}s")
                    first_token_received = True

                final_response_text += token

                # BUFFER JSON
                if stream:
                    if not check_json_done:
                        buffer_detection += token
                        if len(buffer_detection) > 50:
                            if re.match(r"^\s*({|```json)", buffer_detection):
                                is_hidden_json_mode = True
                            else:
                                yield buffer_detection
                            check_json_done = True
                    else:
                        if not is_hidden_json_mode:
                            yield token

            if stream and not check_json_done and not is_hidden_json_mode:
                yield buffer_detection

        except Exception as e:
            self.logger.log_error(
                f"[{correlation_id}] Erreur génération LLM: {e}", exc_info=True
            )
            final_response_text = "Désolé, une erreur interne est survenue."
            llm_success = False
            if stream:
                yield final_response_text

        # ==========================================================
        # 9. TRAITEMENT DU JSON (Post-Génération) & ROUTAGE OUTILS
        # ==========================================================
        if final_response_text:
            # 1. Nettoyage et Parsing Initial
            text_to_parse = re.sub(r"```json\s*", "", final_response_text)
            text_to_parse = re.sub(r"```$", "", text_to_parse.strip())

            # Initialisation de la boucle avec le premier résultat
            current_tool_result = self._detecter_et_executer_function_call(
                text_to_parse
            )

            # Limite de sécurité pour éviter les boucles infinies
            max_autonomy_steps = 10
            step_count = 0

            # 2. Démarrage de la Machine à États
            while current_tool_result and step_count < max_autonomy_steps:
                step_count += 1
                prompt_autonome_obj = None

                # --- A. ROUTAGE STRICT SELON LE RÉSULTAT ---

                # CAS 0 : SORTIE DIRECTE (Final Answer)
                if current_tool_result.get("type") == "FINAL_ANSWER_EXTRACTED":
                    self.logger.info("🏁 SORTIE BOUCLE : Réponse Finale")
                    contenu_final = current_tool_result.get("content", "")
                    if stream and is_hidden_json_mode:
                        yield contenu_final
                    final_response_text = contenu_final
                    break

                # CAS 1 : RÉSULTAT MÉMOIRE (Carte ou Fichier)
                elif current_tool_result.get("type") == "MEMORY_RESULTS":
                    payload = current_tool_result["payload"]
                    item = payload[0] if isinstance(payload, list) and payload else None

                    if item and item.type == "cartographie_projet":
                        self.logger.info("🗺️ ÉTAT: NAVIGATION (CartographyPrompt)")
                        prompt_autonome_obj = CartographyPrompt(
                            prompt_original=prompt,
                            instructions_cartographie=self.agent_parole.recuperer_instruction(
                                "instructions_cartographie"
                            ),
                            cartographie_projet=item.contenu,
                            plan_de_bataille=[
                                self.agent_parole._recuperer_resume_systeme()
                            ],
                            intention=resultat_intention,
                        )

                    elif item and item.type in ["fichier_technique", "fichier_brut"]:
                        self.logger.info(
                            f"🔧 ÉTAT: INSPECTION (FileInspectionPrompt) - {item.titre}"
                        )
                        prompt_autonome_obj = FileInspectionPrompt(
                            prompt_original=prompt,
                            instructions_inspection=self.agent_parole.recuperer_instruction(
                                "instructions_inspection"
                            ),
                            fichier_en_cours=item,
                            notes_precedentes=self.agent_parole._recuperer_resume_systeme(),
                            intention=resultat_intention,
                        )

                    else:
                        if step_count == 1:
                            self.logger.info(
                                "🚀 ÉTAT: STRATÉGIE INITIALE (MemorySearchFirstPrompt)"
                            )
                            prompt_autonome_obj = MemorySearchFirstPrompt(
                                prompt_original=prompt,
                                instructions_first_search=self.agent_parole.recuperer_instruction(
                                    "instructions_memory_search_first_prompt"
                                ),
                                resultats_memoire=payload,
                                intention=resultat_intention,
                            )
                        else:
                            self.logger.info(
                                "🔍 ÉTAT: ENQUÊTE CONTINUE (MemorySearchPrompt)"
                            )
                            prompt_autonome_obj = MemorySearchPrompt(
                                prompt_original=prompt,
                                instructions_memory_search_prompt=self.agent_parole.recuperer_instruction(
                                    "instructions_memory_search_prompt"
                                ),
                                resultats_memoire=payload,
                                raisonnement_precedent=self.active_plan,
                                intention=resultat_intention,
                            )

                # CAS 2 : APRÈS MODIFICATION (Staging Review)
                elif current_tool_result.get("function") == "update_system_summary":
                    self.logger.info("✅ ÉTAT: REVIEW (StagingReviewPrompt)")
                    prompt_autonome_obj = StagingReviewPrompt(
                        prompt_original=prompt,
                        instructions_review=self.agent_parole.recuperer_instruction(
                            "instructions_review"
                        ),
                        etat_staging_actuel=self.agent_parole._recuperer_resume_systeme(),
                        derniere_action=str(
                            current_tool_result.get("results", "Mise à jour effectuée")
                        ),
                        intention=resultat_intention,
                    )

                # CAS 3 : RÉSULTAT GÉNÉRIQUE
                elif "results" in current_tool_result:
                    prompt_autonome_obj = MemorySearchPrompt(
                        prompt_original=prompt,
                        instructions_memory_search_prompt=self.agent_parole.recuperer_instruction(
                            "instructions_memory_search_prompt"
                        ),
                        resultats_memoire=[
                            Souvenir(
                                contenu=str(current_tool_result["results"]),
                                type="tool_result",
                                titre="Resultat Outil",
                                score=1.0,
                            )
                        ],
                        raisonnement_precedent=self.active_plan,
                        intention=resultat_intention,
                    )

                # --- B. GÉNÉRATION DE LA RÉPONSE INTERMÉDIAIRE ---
                # (Ce bloc IF doit être aligné verticalement avec les ELIF ci-dessus)
                if prompt_autonome_obj:
                    # 1. Construction
                    prompt_txt = self.agent_parole.construire_prompt_llm(
                        prompt_autonome_obj
                    )

                    # 2. Génération
                    reponse_interne = ""
                    for token in self.moteur_llm.generer_stream(prompt_txt):
                        reponse_interne += token
                        if stream:
                            yield token

                    # 3. Exécution
                    text_interne_clean = re.sub(r"```json\s*", "", reponse_interne)
                    text_interne_clean = re.sub(r"```$", "", text_interne_clean.strip())

                    next_tool = self._detecter_et_executer_function_call(
                        text_interne_clean
                    )

                    if next_tool:
                        current_tool_result = next_tool
                    else:
                        final_response_text = reponse_interne
                        break
                else:
                    break
        # ==========================================================
        # 10. Post-Traitement Asynchrone (Sauvegarde & Stats)
        # ==========================================================
        self.agent_contexte.mettre_a_jour_historique(prompt, final_response_text)

        if llm_success:
            try:
                interaction_brute = Interaction(
                    prompt=prompt,
                    reponse=final_response_text,
                    system=self.agent_parole.recuperer_instruction(
                        "instructions_systeme"
                    ),
                    intention=prompt_final_obj.intention,
                    contexte_memoire=[],
                    meta=MetadataFichier(
                        id=interaction_id, session_id=session_id, type_memoire="brute"
                    ),
                )
                self.agent_memoire.sauvegarder_interaction_brute(interaction_brute)
            except Exception as e:
                self.logger.log_error(f"Erreur sauvegarde brute : {e}")

            self.current_message_turn += 1
            self.derniere_interaction = (prompt, final_response_text, datetime.now())

            try:
                threading.Thread(
                    target=lambda: self.post_traitement_async(
                        prompt,
                        final_response_text,
                        prompt_final_obj,
                        meta_pipeline.interaction_id,
                        self.current_session_id,
                        self.current_message_turn,
                    ),
                    daemon=True,
                ).start()
            except Exception as e:
                self.logger.log_error(
                    f"Erreur thread post-traitement: {e}", exc_info=True
                )

        if not stream:
            yield final_response_text

    def _gerer_commandes_systeme(self, prompt: str, stream: bool) -> Optional[Dict]:
        """
        [ATOME] Gère les commandes système (+1, -1) et les protocoles (!!!).
        Si une action coupe le flux normal, retourne immédiatement le résultat (yield).
        """
        prompt_clean = prompt.strip()

        # ------🚨 Logique du Protocole ALERTE (!!!)------------
        # - Priorité 1
        # ------------------------------------------------------
        # CORRECTION : On s'assure que "!!!" est explicite et pas juste une partie de code
        # On demande que "!!!" soit au début ou précédé d'un espace, ou seul sur la ligne
        is_alert = "!!!" in prompt_clean and not prompt_clean.startswith(
            "#!"
        )  # Évite le shebang

        if is_alert:
            self.logger.signal_gouvernance(
                "SIGNAL '!!!' DÉTECTÉ. Activation Protocole ALERTE."
            )

            # 1. Lancement analyse réflexive en fond (On garde ça pour les stats/logs)
            try:
                import threading

                threading.Thread(
                    target=lambda: self.agent_reflexor.lancer_analyse_gouvernance(
                        prompt_erreur=prompt,
                        historique=self.agent_contexte.get_historique_chat(),
                    ),
                    daemon=True,
                ).start()
            except Exception:
                pass

            # 2. Construction de l'objet ProtocolePrompt
            # On récupère les ingrédients via Contexte
            contenu_protocole = self.agent_contexte.recuperer_protocole_alerte()
            historique_court = self.agent_contexte.get_historique_recent(limit=10)

            # On force une intention de crise
            intention_forcee = ResultatIntention(
                prompt=prompt,
                sujet=Sujet.SECONDMIND,
                action=Action.DEBUG,
                categorie=Categorie.SYSTEME,
            )

            req_protocole = ProtocolePrompt(
                prompt_original=prompt,
                protocole_contenu=contenu_protocole,
                historique_recent=historique_court,
                intention=intention_forcee,
                regles=[],  # Pas de règles standard, le protocole est la loi
            )

            # On retourne un signal spécial pour 'penser'
            return {"type": "PROTOCOLE_ALERTE", "payload": req_protocole}
        # ------------------------------------------------------
        # DETECTION PREMIER PROMPT
        # ------------------------------------------------------

        p = prompt.lower().strip()

        # Déclencheur conversationnel (STRICT)
        # On ne déclenche le "Lite Mode" que si le message est court (< 10 mots)
        # et contient une salutation. Sinon, on passe par le pipeline complet.
        salutations = ["salut"]
        if any(s == p or (s in p and len(p.split()) < 10) for s in salutations):
            return "NOUVEAU_CHAT"

        # Initialisation par défaut pour éviter UnboundLocalError
        keyword = None
        # ------------------------------------------------------
        # 🚀 Commandes Système (+1, -1)
        # ------------------------------------------------------

        if prompt_clean.startswith("+1") or prompt_clean.startswith("-1"):
            score = 1.0 if prompt_clean.startswith("+1") else 0.0
            mots = prompt_clean.split()
            keyword = mots[1].lower() if len(mots) > 1 else "général"

            # Vérifier qu'on a bien une interaction précédente
            if not (self.derniere_interaction and len(self.derniere_interaction) >= 2):
                return {"response": "Aucune interaction récente à évaluer."}

            original_prompt, final_response_text, *_ = self.derniere_interaction

            # Lancer l'enregistrement dans un thread (pas de lambda capturant l'environnement)
            try:
                import threading
                from functools import partial

                target_fn = partial(
                    self.agent_reflexor.enregistrer_feedback_etendu,
                    prompt=original_prompt,
                    reponse=final_response_text,
                    score=score,
                    mot_cle=keyword,
                )
                threading.Thread(target=target_fn, daemon=True).start()
                self.logger.info(
                    "✅ Enregistrement feedback lancé dans un thread asynchrone."
                )
            except Exception as e:
                self.logger.log_error(f"Échec du lancement du thread de feedback: {e}")
                return {
                    "response": "Erreur interne lors de l'enregistrement du feedback."
                }

            # Réponses synchrones rapides selon mot-clé
            if keyword == "mémoire":
                return {
                    "response": f"🧠 Feedback Mémoire ({'+1' if score else '-1'}) enregistré. Index Whoosh mis à jour."
                }

            if keyword == "pertinence":
                # logique existante de sauvegarde (garde comportement synchrone)
                try:
                    original_prompt, final_response_text, *_ = self.derniere_interaction
                    feedback_data = {
                        "timestamp": datetime.now().isoformat(),
                        "type": "feedback_pertinence_juge",
                        "score_utilisateur": score,
                        "context": {
                            "prompt": original_prompt,
                            "reponse": final_response_text,
                            "classification_precedente": asdict(
                                self.derniere_classification
                            )
                            if self.derniere_classification
                            else None,
                        },
                        "commentaire": "Validé par commande vocale (+1 pertinence)"
                        if score > 0.5
                        else "Invalidé par commande vocale (-1 pertinence)",
                    }
                    status = "ok" if score > 0.5 else "bad"
                    nom_fichier = f"feedback_pertinence/juge_{status}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                    self.agent_memoire.sauvegarder_memoire(
                        contenu=feedback_data,
                        type_memoire="reflexive",
                        nom_fichier=nom_fichier,
                    )
                    return {
                        "response": f"🎯 Feedback Pertinence ({'+1' if score > 0.5 else '-1'}) enregistré. Dataset Juge mis à jour."
                    }
                except Exception as e:
                    self.logger.log_error(f"Erreur sauvegarde feedback pertinence: {e}")
                    return {"response": "Erreur lors de l'enregistrement du feedback."}

            return {
                "response": "✅ Feedback enregistré et traitement asynchrone lancé."
            }
        # -----------------------------------------------------
        # 🚀 Nouvelle Commande : Feedback Intention (-1 intention)
        if not stream and prompt_clean.startswith("-1 intention"):
            # Vérifier si l'interaction précédente et la classification sont disponibles
            if self.derniere_interaction and self.derniere_classification:
                # 1. Obtenir le chemin de sauvegarde (Assumant 'feedback' dans l'Auditor)
                feedback_dir_path = self.auditor.get_path(
                    "feedback", nom_agent="memoire"
                )
                if not feedback_dir_path:
                    self.logger.log_error(
                        "❌ Chemin feedback introuvable dans Auditor."
                    )
                    return {"response": "Erreur: Chemin de feedback introuvable."}

                # 2. Préparer le contenu
                # On utilise l'objet ResultatIntention directement pour le JSON
                original_prompt, _, _ = self.derniere_interaction

                feedback_data = {
                    "timestamp": datetime.now().isoformat(),
                    "prompt_critique": original_prompt,
                    "classification_predite": asdict(
                        self.derniere_classification
                    ),  # ✅ CORRIGÉ
                    "commentaire": "Intention détectée comme incorrecte par l'utilisateur (-1 intention)",
                }

                # 3. Écrire le fichier JSON horodaté (dans le dossier reflexive/feedback)
                dossier = Path(feedback_dir_path)
                dossier.mkdir(parents=True, exist_ok=True)  # Assurer l'existence

                nom_fichier = f"feedback_intention_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                chemin_fichier = dossier / nom_fichier

                try:
                    # Utiliser l'encodeur standardisé pour gérer les Enums et Dataclasses
                    with open(chemin_fichier, "w", encoding="utf-8") as f:
                        # CustomJSONEncoder est dans contrats_interface.py
                        json.dump(
                            feedback_data,
                            f,
                            ensure_ascii=False,
                            indent=2,
                            cls=CustomJSONEncoder,
                        )

                    self.logger.signal_gouvernance(
                        f"✅ Feedback Intention (-1) enregistré: {nom_fichier}"
                    )
                    return {
                        "response": "🎯 Intention de la dernière requête enregistrée comme incorrecte. Analyse à faire."
                    }

                except Exception as e:
                    self.logger.log_error(
                        f"❌ Erreur sauvegarde feedback intention: {e}"
                    )
                    return {
                        "response": "Erreur lors de la sauvegarde du feedback intention."
                    }

            return {
                "response": "Aucune interaction récente avec classification à évaluer."
            }

        return None

    def _handle_forced_search(self, prompt: str, search_mode: str) -> Optional[Any]:
        """
        Gère le mode de recherche forcée (Web uniquement).
        Redirige vers le module Deep Research de l'AgentRecherche.
        """
        if search_mode == "web":
            query = (
                prompt.replace("recherche_web", "").replace("recherche web", "").strip()
            )
            self.logger.info(f"🔍 Deep Research forcée sur : '{query}'")

            # Appel à l'Agent Recherche (qui utilise l'outil RechercheWeb)
            # Cela peut prendre du temps (boucle Search -> Read -> Evaluate)
            rapport_final = self.agent_recherche.recherche_web_profonde(query)

            # On renvoie le rapport complet comme réponse unique
            # (Note : Ce n'est pas streamé token par token, c'est un bloc de texte)
            yield rapport_final
            return

        return None

    def post_traitement_async(
        self,
        prompt: str,
        reponse: str,
        standard_prompt: StandardPrompt,
        interaction_id: str,
        session_id: str,
        message_turn: int,
    ):
        """
        Tâches de fond (Fire-and-Forget).

        Exécuté dans un Thread Daemon pour ne pas bloquer la réponse utilisateur (UI Latency).
        Responsabilités :
        1. **Code Extraction** : Parsing de la réponse pour extraire/sauvegarder les snippets (.py).
        2. **Sanitization** : Nettoyage des données (retrait du contenu brut des fichiers) avant stockage.
        3. **Persistance** : Écriture du log JSON final (Interaction) via AgentMemoire.
        4. **Juge** : Évaluation asynchrone de la qualité de la réponse (si activé).
        """
        try:
            reponse_pour_historique = reponse
            # ===========================================================
            # 1. EXTRACTION & TRAITEMENT DU CODE (Nouveau Pipeline)
            # ===========================================================
            if getattr(self, "agent_code", None):
                try:
                    # On demande à l'AgentCode de séparer le texte du code
                    texte_nettoye_api, artefacts = (
                        self.agent_code.extractor_manager.traiter_reponse_llm(reponse)
                    )

                    # A. Sauvegarde des fichiers physiques (si code détecté)
                    if artefacts:
                        self.agent_memoire.sauvegarder_artefacts_code(artefacts)
                        self.dernier_code_hash = artefacts[-1]["hash"]

                    # B. On récupère le texte nettoyé par l'API (s'il existe, sinon on garde l'original)
                    if texte_nettoye_api:
                        reponse_pour_historique = texte_nettoye_api

                except Exception as e:
                    self.logger.log_error(f"Erreur extraction code: {e}")

            # ===========================================================
            # 1-BIS. NETTOYAGE ULTIME (Sécurité Regex)
            # ===========================================================
            # Même si l'AgentCode a raté son coup, on FORCE le retrait visuel des blocs de code
            # pour ne pas polluer le JSON historique avec des milliers de lignes de code.
            import re

            pattern_code = r"```[\s\S]*?```"
            if re.search(pattern_code, reponse_pour_historique):
                reponse_pour_historique = re.sub(
                    pattern_code,
                    "\n\n[... 💾 CODE EXTRAIT ET SAUVEGARDÉ DANS /memoire/code/ ...]\n\n",
                    reponse_pour_historique,
                )

            # ===========================================================
            # 2. PRÉPARATION SÉCURISÉE DES DONNÉES (Fix du Crash)
            # ===========================================================
            # On utilise des listes vides par défaut si standard_prompt est None
            souvenirs = getattr(standard_prompt, "souvenirs", []) or []
            # B. Le Contexte Technique/Législatif -> Pour 'meta.data_libre'
            # On utilise asdict pour sérialiser proprement en JSON
            regles_objs = getattr(standard_prompt, "regles", []) or []
            docs_objs = getattr(standard_prompt, "fichiers_readme", []) or []
            code_objs = (
                getattr(
                    standard_prompt,
                    "code_chunks",
                    getattr(standard_prompt, "contexte_code", []),
                )
                or []
            )

            # Conversion en dict pour stockage JSON dans data_libre
            regles_data = [asdict(r) for r in regles_objs]
            docs_data = [asdict(d) for d in docs_objs]
            # Pour le code, on gère le cas où ce n'est pas une dataclass pure (parfois dict)
            code_data = []
            for c in code_objs:
                if is_dataclass(c):
                    code_data.append(asdict(c))
                elif isinstance(c, dict):
                    code_data.append(c)
                else:
                    code_data.append({"contenu": str(c)})
            # ===========================================================
            # 3. JUGE (Si actif)
            # ===========================================================
            valide_juge = True
            score_juge = 1.0
            raison_juge = "Pas de juge actif"

            if getattr(self, "agent_juge", None):
                try:
                    contexte_str = "\n".join([s.contenu for s in souvenirs + docs_objs])
                    res_juge = self.agent_juge.evaluer_coherence_reponse(
                        contexte_rag_str=contexte_str,
                        prompt=prompt,
                        reponse=reponse_pour_historique,
                    )
                    valide_juge = res_juge.valide
                    score_juge = res_juge.score
                    raison_juge = res_juge.raison
                except Exception:
                    pass
            # ===========================================================
            # 4. GÉNÉRATION DU RÉSUMÉ (MiniLLM)
            # ===========================================================
            resume_interaction = "Échange standard."
            if getattr(self, "moteur_mini_llm", None):
                try:
                    p_resume = f"Résumé 1 phrase:\nUser: {prompt[:300]}\nAssistant: {reponse_pour_historique[:300]}"
                    # On consomme le générateur
                    resume_interaction = "".join(
                        list(self.moteur_mini_llm.generer_stream(p_resume))
                    )
                except Exception:
                    pass

            # ===========================================================
            # 🛡️ PURGE MÉMOIRE
            # On ne veut PAS sauvegarder le contenu des fichiers lus dans l'historique.
            # On garde la référence (titre/chemin) mais on vide le contenu texte.
            # ===========================================================
            souvenirs_nettoyes = []
            for s in souvenirs:
                # Si c'est un fichier technique ou du code, on vide le contenu
                if s.type in [
                    "fichier_technique",
                    "fichier_brut",
                    "code",
                    "fichier_actif",
                ]:
                    # On crée une COPIE pour ne pas casser l'affichage immédiat si nécessaire
                    from dataclasses import replace

                    s_clean = replace(
                        s,
                        contenu=f"[Fichier '{s.titre}' consulté - Contenu non persisté dans l'historique]",
                    )
                    souvenirs_nettoyes.append(s_clean)
                else:
                    souvenirs_nettoyes.append(s)

            # On fait pareil pour les chunks de code
            code_objs_nettoyes = []
            for c in code_objs:
                # Si c'est une Dataclass, on remplace
                if is_dataclass(c):
                    from dataclasses import replace

                    # On garde juste la signature/nom
                    nom = getattr(c, "chemin", getattr(c, "name", "Inconnu"))
                    c_clean = replace(
                        c, contenu=f"[Snippet '{nom}' utilisé - Non persisté]"
                    )
                    code_objs_nettoyes.append(c_clean)
                else:
                    code_objs_nettoyes.append(
                        c
                    )  # Cas dictionnaire, on laisse (ou on nettoie si besoin)

            # ===========================================================
            # 5. CONSTRUCTION MÉTADONNÉES & SAUVEGARDE
            # ===========================================================

            # Agrégation des noms de fichiers pour la traçabilité rapide
            fichiers_vus = [s.titre for s in souvenirs]
            fichiers_vus.extend([f"REGLE:{r.titre}" for r in regles_objs])
            fichiers_vus.extend([f"DOC:{d.titre}" for d in docs_objs])
            for c in code_objs:
                nom = getattr(c, "chemin", getattr(c, "name", "Snippet"))
                fichiers_vus.append(f"CODE:{nom}")

            meta_fichier = MetadataFichier(
                id=interaction_id,
                session_id=session_id,
                message_turn=message_turn,
                source_agent="Semi",
                fichiers_consultes=fichiers_vus,
                validation_juge=valide_juge,
                score_qualite=score_juge,
                details_juge=raison_juge,
                len_contenu=len(reponse_pour_historique),
                # ✅ STOCKAGE SÉPARÉ : On garde la trace sans polluer les souvenirs
                data_libre={
                    "resume_semantique": resume_interaction,
                    "contexte_technique": "RAG Code" if code_objs else "Standard",
                    "snapshot_regles": regles_data,
                    "snapshot_fichiers_readme": docs_data,
                    "snapshot_code": code_data,
                },
            )

            # Création de l'objet Interaction avec typage STRICT
            interaction_obj = Interaction(
                prompt=prompt,
                reponse=reponse_pour_historique,
                system="Instructions Système",
                intention=getattr(standard_prompt, "intention", None),
                # ✅ CORRECTIF FINAL : Uniquement des Souvenirs ici
                contexte_memoire=souvenirs_nettoyes,
                meta=meta_fichier,
            )

            # 🛡️👁️‍🗨️🛡️# VALIDATION FORMAT SORTIE
            # On vérifie l'intégrité avant d'écrire sur le disque
            self.auditor.valider_format_sortie(interaction_obj)

            self.agent_memoire.memoriser_interaction(interaction_obj)

        except Exception as e:
            self.logger.log_error(
                f"❌ Erreur CRITIQUE post-traitement: {e}", exc_info=True
            )

    # MÉCANIQUE DE BATCH DE VECTORISATION PERSISTANTE AU DÉMARRAGE
    # ===========================================================
    def _verifier_batch_au_demarrage(self):
        """
        Vérifie si le traitement batch différé doit être lancé au démarrage.
        Se déclenche si le dernier run date de plus de 45h ou n'existe pas.
        """
        try:
            state = self.processeur_batch._charger_etat()
            dernier_run_str = state.get("dernier_run")

            # CAS 1 : Premier lancement ou état perdu
            if not dernier_run_str:
                self.logger.info(
                    "🕒 Aucun batch précédent détecté. Lancement asynchrone immédiat."
                )
                # ✅ CORRECTION : Lancement dans un thread pour ne pas bloquer le démarrage du serveur
                self._lancer_batch_async()
                return

            # CAS 2 : Vérification du délai
            dernier_run = datetime.fromisoformat(dernier_run_str)
            delta = datetime.now() - dernier_run
            heures_ecoulees = delta.total_seconds() / 3600

            if heures_ecoulees >= 45:
                self.logger.info(
                    f"🕒 Batch obsolète ({heures_ecoulees:.1f}h). Lancement asynchrone..."
                )
                self._lancer_batch_async()
            else:
                self.logger.info(
                    f"✅ Batch récent ({heures_ecoulees:.1f}h). Aucune action."
                )

        except Exception as e:
            self.logger.log_error(f"Erreur vérification batch: {e}")

    def _lancer_batch_async(self):
        """
        Lance le traitement batch (consolidation mémoire) dans un thread séparé.
        Appelé par _verifier_batch_au_demarrage.
        """
        try:
            import threading

            threading.Thread(
                target=self.processeur_batch.traiter_batch_differe, daemon=True
            ).start()
            self.logger.info("🚀 Batch de vectorisation lancé en arrière-plan.")
        except Exception as e:
            self.logger.log_error(f"Échec lancement batch async: {e}")

    # ----------------------------------------------------------------
    # CAPACITÉS COGNITIVES (RAG ARCHITECTURE & CODE)
    # ----------------------------------------------------------------

    def consulter_architecture_et_code(self, question: str) -> str:
        """
        Outil critique : À utiliser dès que tu dois répondre à une question sur
        le fonctionnement interne, le code, les fichiers ou l'architecture du projet.
        Permet de lire le code source réel du projet.

        Args:
            question (str): La question technique précise (ex: "Comment fonctionne agent_Memoire ?")

        Returns:
            str: Un résumé contextuel contenant les bouts de code pertinents.
        """
        if not self.agent_code:
            return "Indisponible : Le module RAG Code n'est pas initialisé."

        self.logger.log_info(f"🏗️ Je consulte l'architecture code pour : {question}")

        # On délègue à l'adapter qui gère la complexité (vecteurs + graphe)
        contexte = self.agent_code.fournir_contexte(question)

        return contexte

    def _exec_update_system_summary(self, new_content: str) -> str:
        """
        Met à jour etat_systeme_resume.md dans le dossier de l'agent.
        Mode: APPEND (Ajout) pour conserver l'historique des modifications.
        """
        try:
            from datetime import datetime
            from pathlib import Path

            # 1. Localisation (Dossier Semi)
            path_semi_dir = self.auditor.get_path("agent_dir")
            # Fallback si l'auditor ne répond pas (ex: test unitaire)
            if not path_semi_dir:
                path_semi_dir = Path(__file__).parent

            f_dest = Path(path_semi_dir) / "etat_systeme_resume.md"

            # 2. Préparation de l'horodatage
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

            # Si le fichier n'existe pas encore, on le crée avec un en-tête
            if not f_dest.exists():
                with open(f_dest, "w", encoding="utf-8") as f:
                    f.write(f"# 🧠 ÉTAT SYSTÈME & RÉSUMÉ\n_Initialisé le {now_str}_\n")

            # 3. Préparation du bloc à ajouter
            # On ajoute un saut de ligne propre avant le nouveau bloc
            bloc_ajout = f"\n\n### 📅 Mise à jour du {now_str}\n{new_content}\n---"

            # 4. Écriture en mode AJOUT ('a')
            with open(f_dest, "a", encoding="utf-8") as f:
                f.write(bloc_ajout)

            self.logger.info(f"📝 Résumé système mis à jour (Ajout) : {f_dest.name}")
            return f"Succès : Information ajoutée à {f_dest.name}."

        except Exception as e:
            self.logger.log_error(f"Erreur écriture résumé : {e}")
            return f"Erreur critique : {e}"

    def _extraire_bloc_json(self, texte: str) -> str:
        """
        Extrait le premier bloc JSON valide en comptant les accolades imbriquées,
        tout en ignorant celles contenues dans les chaînes de caractères.
        """
        texte = texte.strip()
        idx_debut = texte.find("{")
        if idx_debut == -1:
            return ""

        compteur = 0
        in_string = False
        escape = False

        for i, char in enumerate(texte[idx_debut:], start=idx_debut):
            # 1. Gestion de l'état "Dans une chaîne de caractères"
            if char == '"' and not escape:
                in_string = not in_string

            # 2. Gestion de l'échappement (ex: \" à l'intérieur d'une chaîne)
            if char == "\\" and not escape:
                escape = True
                continue  # On saute le backslash pour ne pas le traiter deux fois

            escape = False  # Reset de l'échappement pour le caractère suivant

            # 3. Comptage des accolades (UNIQUEMENT si on n'est pas dans une string)
            if not in_string:
                if char == "{":
                    compteur += 1
                elif char == "}":
                    compteur -= 1
                    # Quand on retombe à 0, c'est la fin du JSON
                    if compteur == 0:
                        return texte[idx_debut : i + 1]

        return ""

    # =========================================================================
    # 🔧 GESTION DES OUTILS (VERSION ROBUSTE RESTAURÉE)
    # =========================================================================

    def _detecter_et_executer_function_call(self, response: str) -> Optional[Dict]:
        """
        Parseur et Dispatcheur d'Outils (Function Calling local).

        Analyse la réponse textuelle pour extraire un bloc JSON valide (gestion des accolades imbriquées).
        Mappe le champ "function" vers les méthodes internes :
        - `recherche_web` -> AgentRecherche (Deep Search)
        - `rechercher_memoire` -> RechercheMemoireTool (RAG/Files)
        - `update_system_summary` -> Mise à jour du fichier d'état global.

        Returns:
            Dict: Le résultat de l'exécution de l'outil (souvent injecté dans le prompt suivant).
        """
        import json
        import re

        # 1. Extraction ROBUSTE (Récupération de ta méthode logicielle)
        json_str = self._extraire_bloc_json(response)
        if not json_str:
            return None

        # 2. Nettoyage
        json_str = json_str.replace("```json", "").replace("```", "").strip()

        # 3. Parsing & Réparation (Chemins Windows - CRITIQUE & CORRIGÉ)
        try:
            # 🛑 CORRECTION MAJEURE : Negative Lookbehind (?<!\\)
            # Cette regex dit : "Remplace le \ par \\ SEULEMENT S'IL N'EST PAS DÉJÀ PRÉCÉDÉ d'un \"
            # Ainsi : "D:\Dev" devient "D:\\Dev" (Fixé)
            # Mais :  "D:\\Dev" reste "D:\\Dev" (Pas touché)
            json_str_fixed = re.sub(r'(?<!\\)\\(?![/u"\\bfnrt])', r"\\\\", json_str)

            function_call = json.loads(json_str_fixed)

        except json.JSONDecodeError:
            # Fallback ultime : Si le JSON est vraiment cassé, on tente le mode permissif "strict=False"
            try:
                function_call = json.loads(json_str, strict=False)
            except Exception:
                self.logger.log_warning(f"Échec parsing JSON final: {json_str[:50]}...")
                return None

        # 4. Capture du PLAN (State Passing - CRITIQUE POUR AUTONOMIE)
        if "plan_update" in function_call:
            self.active_plan = function_call["plan_update"]
            self.logger.info(f"📅 Plan mis à jour : {len(self.active_plan)} étapes.")

        # Gestion de la structure imbriquée (next_action) ou plate
        action_data = function_call.get("next_action", function_call)

        # CAS 0 : RÉPONSE FINALE
        if isinstance(action_data, dict) and action_data.get("type") == "final_answer":
            return {
                "type": "FINAL_ANSWER_EXTRACTED",
                "content": action_data.get("content", ""),
            }

        function_name = action_data.get("function")
        arguments = action_data.get("arguments", {})
        if not function_name:
            return None

        # 5. EXÉCUTION (Restauration intégrale des outils + Ajouts)
        try:
            self.logger.info(f"⚙️ Tentative exécution outil : {function_name}")

            # --- OUTIL : RECHERCHE WEB ---
            if function_name == "recherche_web":
                query = arguments.get("query", "")
                # On utilise l'agent recherche s'il a la capacité, sinon fallback
                if hasattr(self.agent_recherche, "recherche_web_profonde"):
                    rapport = self.agent_recherche.recherche_web_profonde(query)
                    return {"function": function_name, "results": rapport}
                return {
                    "function": function_name,
                    "results": "Recherche web non disponible.",
                }

            # --- OUTIL : MÉMOIRE (Délégué à RechercheMemoireTool) ---
            elif function_name == "rechercher_memoire":
                if not hasattr(self.agent_recherche, "outil_recherche_memoire"):
                    return {
                        "function": function_name,
                        "results": "Erreur: Outil mémoire non chargé.",
                    }

                # Support caché pour lire_cartographie via query
                q = arguments.get("query", "")
                if "cartographie" in q.lower() or "project_map" in q.lower():
                    return self.agent_recherche.outil_recherche_memoire.traiter_lecture_cartographie(
                        {}
                    )

                return self.agent_recherche.outil_recherche_memoire.traiter_recherche_memoire(
                    arguments
                )

            # --- OUTIL : CARTOGRAPHIE (Nouveau Standard) ---
            elif function_name == "lire_cartographie":
                if not hasattr(self.agent_recherche, "outil_recherche_memoire"):
                    return {
                        "function": function_name,
                        "results": "Erreur: Outil mémoire non chargé.",
                    }
                return self.agent_recherche.outil_recherche_memoire.traiter_lecture_cartographie(
                    {}
                )

            # --- OUTIL : SYSTÈME ---
            elif function_name == "update_system_summary":
                content = arguments.get("content", "")
                # CORRECTION : Appel de la méthode qui accepte (new_content)
                result = self._exec_update_system_summary(content)
                return {"function": function_name, "results": result}

            # --- OUTIL : FINAL ANSWER (Explicite) ---
            elif function_name == "final_answer":
                return {
                    "type": "FINAL_ANSWER_EXTRACTED",
                    "content": arguments.get("content", "Terminé."),
                }

            else:
                return {
                    "function": function_name,
                    "results": f"Outil inconnu : {function_name}",
                }

        except Exception as e:
            self.logger.log_error(f"Erreur exécution tool {function_name}: {e}")
            return {"function": function_name, "results": f"Exception technique : {e}"}

    # =================================================================
    # 🧠 PROPRIOCEPTION : GÉNÉRATION DU RÉSUMÉ SYSTÈME (Ancrage Root)
    # =================================================================
    def actualiser_resume_systeme(self):
        """
        Proprioception : Met à jour le fichier 'etat_systeme_resume.md'.

        Lit les fichiers de logs (historique, todo) pour construire une "conscience de soi"
        à jour, qui sera injectée dans le System Prompt de la prochaine requête.
        Assure que l'agent sait ce qu'il a fait la veille.
        """
        try:
            self.logger.info("🧠 Mise à jour de la Conscience du Système...")

            # 1. Récupération du dossier via l'Auditor
            # On demande le chemin 'agent_dir' configuré pour 'semi'
            dossier_semi = Path(self.auditor.get_path("agent_dir"))

            if not dossier_semi.exists():
                self.logger.log_error(
                    f"Dossier Semi introuvable via Auditor : {dossier_semi}"
                )
                return False

            f_hist = dossier_semi / "historique_secondmind.md"
            f_todo = dossier_semi / "todo_secondmind.md"
            f_dest = dossier_semi / "etat_systeme_resume.md"

            # 2. Création si absent (Initialisation)
            if not f_hist.exists():
                f_hist.write_text(
                    "# Historique SecondMind\n\n## Initialisation", encoding="utf-8"
                )
            if not f_todo.exists():
                f_todo.write_text(
                    "# TODO SecondMind\n\n## Priorité Haute", encoding="utf-8"
                )

            # 3. Lecture Simple (5 premières lignes)
            # (On garde votre logique simplifiée sans LLM pour l'instant, comme demandé précédemment)
            def get_top_5_lines(path):
                try:
                    text = path.read_text(encoding="utf-8")
                    lines = [line.strip() for line in text.splitlines() if line.strip()]
                    return lines[:5]
                except Exception as e:
                    return [f"Erreur lecture: {e}"]

            hist_lines = get_top_5_lines(f_hist)
            todo_lines = get_top_5_lines(f_todo)

            # 4. Assemblage
            contenu_final = f"""# Résumé de l’état du système
_Mise à jour : {datetime.now().strftime("%Y-%m-%d %H:%M")}_

## 📜 Historique (Récent)

"""
            for ligne in hist_lines:
                contenu_final += f"- {ligne}\n"

            contenu_final += "\n## 📝 À Faire (Prioritaire)\n"
            for ligne in todo_lines:
                contenu_final += f"- {ligne}\n"

            contenu_final += "\n## 📊 État Global\nSystème actif."

            # 5. Écriture
            f_dest.write_text(contenu_final, encoding="utf-8")
            self.logger.info(f"✅ Résumé mis à jour dans : {f_dest}")
            return True

        except Exception as e:
            self.logger.log_error(f"Erreur Proprioception : {e}")
            return False

    ##############################################
    # Méthode pour gérer le contexte du frontend #
    ##############################################
    def _format_manual_context(self, manual_context: List[Dict]) -> str:
        """Formate le contexte manuel des slots en string pour agent_Parole"""
        if not manual_context:
            return None

        formatted = ""
        for slot in manual_context:
            title = slot.get("title", "Slot")
            content = slot.get("content", "")
            formatted += f"\n### {title}\n{content}\n"

        self.logger.log_thought(f"Contexte manuel formaté: {len(formatted)} caractères")
        return formatted

    ##############################################
    # Méthode pour la synchronisation des stats #
    ##############################################
    def obtenir_etat_cognitif(self) -> Dict[str, Dict]:
        """
        Agrégateur de métriques pour le Dashboard.

        Collecte les statistiques de tous les sous-agents (Memoire, Recherche, LLM)
        et les normalise pour l'affichage frontend.
        Gère les cas où un agent n'est pas initialisé (Graceful degradation).

        Returns:
            Dict avec les stats de chaque agent au format:
            {
                "AgentMemoire": {
                    "appels_total": int,
                    "erreurs_total": int,
                    "temps_moyen_ms": float,
                    "stats_specifiques": dict
                },
                ...
            }
        """
        etat_cognitif = {}

        # Liste des agents à interroger
        agents_a_interroger = [
            ("AgentMemoire", self.agent_memoire),
            ("AgentRecherche", self.agent_recherche),
            ("AgentContexte", self.agent_contexte),
            ("AgentParole", self.agent_parole),
            ("AgentJuge", self.agent_juge),
            ("AgentReflexor", self.agent_reflexor),
            ("MoteurLLM", self.moteur_llm),
            ("MoteurMiniLLM", self.moteur_mini_llm),
            ("IntentionDetector", self.intention_detector),
        ]

        for nom_agent, instance_agent in agents_a_interroger:
            try:
                # Vérifier si l'agent a un stats_manager
                if (
                    hasattr(instance_agent, "stats_manager")
                    and instance_agent.stats_manager
                ):
                    # ✅ L'ASTUCE EST ICI : On crée une variable typée
                    manager: StatsBase = instance_agent.stats_manager
                    stats = manager.obtenir_statistiques()
                    etat_cognitif[nom_agent] = {
                        "appels_total": stats.get("appels_total", 0),
                        "erreurs_total": stats.get("erreurs_total", 0),
                        "temps_moyen_ms": 0,  # StatsBase n'a pas temps_moyen_ms
                        "stats_specifiques": stats.get("stats_specifiques", {}),
                    }
                else:
                    # Fallback si pas de stats_manager
                    etat_cognitif[nom_agent] = {
                        "appels_total": 0,
                        "erreurs_total": 0,
                        "temps_moyen_ms": 0,
                        "stats_specifiques": {},
                    }
                    self.logger.log_warning(f"⚠️ {nom_agent} n'a pas de stats_manager")

            except Exception as e:
                self.logger.log_error(
                    f"Erreur lors de la collecte des stats pour {nom_agent}: {e}"
                )
                etat_cognitif[nom_agent] = {
                    "appels_total": 0,
                    "erreurs_total": 0,
                    "temps_moyen_ms": 0,
                    "stats_specifiques": {},
                    "erreur": str(e),
                }

        # Ajouter les stats propres de Semi
        try:
            if hasattr(self, "stats_manager") and self.stats_manager:
                stats_semi = self.stats_manager.obtenir_statistiques()
                etat_cognitif["AgentSemi"] = {
                    "appels_total": stats_semi.get("appels_total", 0),
                    "erreurs_total": stats_semi.get("erreurs_total", 0),
                    "temps_moyen_ms": 0,
                    "stats_specifiques": stats_semi.get("stats_specifiques", {}),
                }
        except Exception as e:
            self.logger.log_error(
                f"Erreur lors de la collecte des stats pour AgentSemi: {e}"
            )

        self.logger.info(f"📊 État cognitif collecté pour {len(etat_cognitif)} agents")
        return etat_cognitif


# --- ZONE DE TEST ARCHITECTE ---
if __name__ == "__main__":
    print("🚀 Démarrage du mode TEST ISOLÉ pour Agent Semi...")

    try:
        # 1. Instanciation
        agent_test = AgentSemi()
        print(f"✅ Agent prêt : {agent_test}")

        # 2. DÉCLENCHEMENT DU FLUX (Simulation d'une question utilisateur)
        print("🏁 Envoi de la requête 'Qui es-tu ?'...")

        # On appelle la méthode principale comme le ferait le serveur
        # Note : penser() est un générateur, il faut boucler dessus pour l'exécuter
        generateur = agent_test.penser("Qui es-tu ?", stream=False)

        for bout_de_reponse in generateur:
            print(f"📤 Sortie reçue : {bout_de_reponse}")

    except Exception as e:
        print(f"❌ ERREUR FLUX : {e}")
        raise e
