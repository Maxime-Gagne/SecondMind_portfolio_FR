#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ruff: noqa: E402
"""
ProcesseurBrutePersistante - Moteur de Consolidation Épisodique Asynchrone
Module responsable de la transformation des logs bruts (Short-Term Memory) en souvenirs structurés (Long-Term Memory).

Ce module implémente le processus de "Sommeil Cognitif" : il attend la fin d'une session d'activité
pour analyser l'ensemble des échanges avec le recul nécessaire, garantissant une classification
plus précise que l'analyse temps réel.

Stratégie "Global Context, Granular Storage" :
    1. **Agrégation** : Regroupe tous les messages d'une session (vision globale).
    2. **Analyse Batch** : Envoie le transcript complet au LLM pour comprendre le fil conducteur.
    3. **Atomisation** : Découpe la réponse du LLM en souvenirs individuels standardisés.
    4. **Double Injection** : Alimente simultanément la mémoire persistante (pour le RAG)
       et le Dataset d'entraînement (pour le Fine-Tuning futur).
==========================================================================
Workflow :
1. Scanne 'historique' et regroupe par SESSION ID.
2. Attend la fin de session (Time-out > 4h ou Test immédiat).
3. Envoie TOUT le transcript au LLM pour analyse contextuelle globale.
4. Le LLM génère une série de blocs "Micro-Résumés" cohérents entre eux.
5. Le script découpe cette réponse et sauvegarde 1 fichier JSON par interaction.
6. Vectorisation individuelle.
"""

import sys
import json
import yaml
import hashlib
from pathlib import Path
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import logging
import re
import time

# Imports système
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agentique.base.META_agent import AgentBase
from agentique.base.contrats_interface import (
    CustomJSONEncoder,
    Interaction,
    MetadataFichier,
    ResultatIntention,
    Sujet,
    Action,
    Categorie,
    Souvenir,
)
from agentique.sous_agents_gouvernes.agent_Memoire.moteur_vecteur import MoteurVectoriel
from agentique.sous_agents_gouvernes.agent_Recherche.agent_Recherche import (
    AgentRecherche,
)
from agentique.sous_agents_gouvernes.agent_Parole.moteurs.moteur_llm import MoteurLLM
from agentique.sous_agents_gouvernes.agent_Entraineur.auto_dataset_builder import (
    AutoDatasetBuilder,
)

logger = logging.getLogger(__name__)


class ProcesseurBrutePersistante(AgentBase):
    def __init__(self, llm_engine=None):
        super().__init__(nom_agent="ProcesseurBrutePersistante")
        """
        Agent de maintenance cognitive opérant en arrière-plan (Daemon).

        Il surveille le dossier 'historique', détecte les sessions inactives (Timeout) et
        déclenche le pipeline de consolidation. Il gère l'état d'avancement (State Management)
        pour éviter de re-traiter les fichiers et assure l'intégrité de la transition
        entre la mémoire volatile et la mémoire cristallisée.

        Attributes:
            delai_timeout_heures (int): Seuil d'inactivité déclenchant la consolidation.
            dataset_builder (AutoDatasetBuilder): Module de génération automatique de données d'entraînement (Self-Learning).
        """

        # 1. Chargement Config (Source de Vérité)
        self.config = self._load_config()
        self.proc_config = self.config.get("processeur_persistante", {})

        # 2. Paramètres dynamiques
        self.delai_timeout_heures = self.proc_config.get("timeout_session_heures", 4)

        self.moteur_vectoriel = MoteurVectoriel()
        self.agent_recherche = AgentRecherche()

        if llm_engine:
            self.llm_synthese = llm_engine
        else:
            self.llm_synthese = MoteurLLM()

        self.source_dir = Path(self.auditor.get_path("historique", nom_agent="memoire"))
        self.persistante_dir = Path(
            self.auditor.get_path("persistante", nom_agent="memoire")
        )
        self.state_file = (
            Path(self.auditor.get_path("base", nom_agent="memoire"))
            / ".traitement_state.json"
        )

        self.state = self._charger_etat()
        self.fichiers_ignores = set(self.state.get("fichiers_historiques_traites", []))
        self.dataset_builder = AutoDatasetBuilder()

        self.logger.info(
            f"🧠 Processeur Initialisé (Timeout: {self.delai_timeout_heures}h)."
        )

    def _load_config(self):
        path = self.auditor.get_path("config", "memoire")
        if path and Path(path).exists():
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f).get("configuration", {})
        return {}

    def _charger_etat(self) -> Dict:
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _sauver_etat(self):
        self.state["fichiers_historiques_traites"] = list(self.fichiers_ignores)
        self.state["dernier_run"] = datetime.now().isoformat()
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self.state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.log_error(f"Erreur sauvegarde état: {e}")

    def traiter_batch_differe(self):
        """
        Orchestrateur du pipeline de traitement différé.

        Exécute la boucle principale :
        1. Identifie les sessions terminées (delta temps > timeout).
        2. Lance l'analyse sémantique globale via le LLM.
        3. Sauvegarde les résultats sous forme d'objets 'Interaction' enrichis.
        4. Déclenche la vectorisation et l'indexation des nouveaux souvenirs.
        5. Alimente le dataset d'entraînement avec les paires (Prompt Original / Intention Corrigée).

        Returns:
            Dict: Rapport d'exécution contenant le nombre d'items traités.
        """
        self.logger.info("🕒 Regroupement des sessions en attente...")
        sessions = self._grouper_fichiers_par_session()
        count = 0

        for session_id, data in sessions.items():
            messages = data["messages"]

            # --- LOGIQUE TIME-OUT ---
            # Pour le mode "Temps réel", mettez le timedelta à 0
            if (datetime.now() - data["last_timestamp"]) > timedelta(
                hours=self.delai_timeout_heures
            ):
                nb_msgs = len(messages)
                self.logger.info(
                    f"🔒 Consolidation session {session_id[:8]} ({nb_msgs} messages)..."
                )

                try:
                    # 1. Traitement GLOBAL de la session (Batch LLM)
                    resultats_resumes = self._analyser_session_complete(
                        messages, session_id
                    )

                    if resultats_resumes:
                        # 2. Sauvegarde Granulaire
                        for i, interaction_resume in enumerate(resultats_resumes):
                            # On récupère les métadonnées originales pour le lien
                            data_orig = messages[i]
                            fichier_source = data["files"][i]

                            # --- 🧠 LOGIQUE DATASET 🧠 ---
                            # On récupère le VRAI prompt utilisateur (pas le "Résumé 1/5")
                            vrai_prompt = data_orig.get("prompt") or data_orig.get(
                                "user", ""
                            )

                            # On crée une interaction hybride pour l'entraînement :
                            if vrai_prompt and interaction_resume.intention:
                                training_interaction = Interaction(
                                    prompt=vrai_prompt,
                                    reponse="",  # On s'en fiche pour l'intention detector
                                    intention=interaction_resume.intention,
                                    contexte_memoire=[],
                                    system="",
                                    meta=MetadataFichier(),
                                )
                                self.dataset_builder.ajouter_interaction(
                                    training_interaction, source="batch_qwen14b"
                                )
                            # ------------------------------

                            # Sauvegarde du résumé (Inchangé)
                            path = self._sauvegarder_resume(
                                interaction_resume, data_orig
                            )

                            # Vectorisation (Inchangé)
                            self._indexer_resume(interaction_resume, path)

                            # Marquage
                            self.fichiers_ignores.add(fichier_source)
                            count += 1

                        self.logger.info(
                            f"✅ Session {session_id[:8]} archivée et injectée dans le dataset."
                        )
                except Exception as e:
                    self.logger.log_error(
                        f"Erreur traitement session {session_id}: {e}"
                    )

        # Sauvegarde état
        self._sauver_etat()
        return {"items_traites": count}

    def _grouper_fichiers_par_session(self) -> Dict:
        """Groupe les fichiers non traités par session_id"""
        sessions = {}
        files = sorted(
            list(self.source_dir.rglob("*.json"))
        )  # Tri important pour l'ordre chrono

        for fichier in files:
            if fichier.name in self.fichiers_ignores:
                continue
            try:
                with open(fichier, "r", encoding="utf-8") as fd:
                    data = json.load(fd)
                meta = data.get("meta", {})
                sid = meta.get("session_id") or data.get("session_id") or "unknown"
                ts_str = meta.get("timestamp") or data.get("timestamp")
                try:
                    ts = datetime.fromisoformat(str(ts_str))
                except Exception:
                    ts = datetime.now()

                if sid not in sessions:
                    sessions[sid] = {"messages": [], "last_timestamp": ts, "files": []}
                sessions[sid]["messages"].append(data)
                sessions[sid]["files"].append(fichier.name)
                if ts > sessions[sid]["last_timestamp"]:
                    sessions[sid]["last_timestamp"] = ts
            except Exception:
                continue

        # Tri chronologique des messages dans chaque session
        for s in sessions:
            # On trie les paires (message, fichier) ensemble
            zipped = sorted(
                zip(sessions[s]["messages"], sessions[s]["files"]),
                key=lambda pair: pair[0].get("meta", {}).get("timestamp", ""),
            )
            sessions[s]["messages"] = [z[0] for z in zipped]
            sessions[s]["files"] = [z[1] for z in zipped]

        return sessions

    def _analyser_session_complete(
        self, messages: List[Dict], session_id: str
    ) -> List[Interaction]:
        """
        Cœur cognitif du processeur : Analyse Batch Contextuelle.

        Construit un prompt massif contenant l'intégralité du transcript de la session.
        Force le LLM à agir comme un "Superviseur" qui re-qualifie chaque message
        avec le recul de la conversation entière (ex: comprendre que "ça marche pas"
        fait référence au code envoyé 3 messages plus tôt).

        Applique une taxonomie stricte (Sujet/Action/Catégorie) et impose un format
        de sortie JSON séquentiel pour un parsing robuste.

        Args:
            messages (List[Dict]): La liste chronologique des logs bruts.
            session_id (str): Identifiant unique de la session (pour traçabilité).

        Returns:
            List[Interaction]: Liste d'objets standardisés prêts pour la persistance.
        """
        # --- CHRONO DÉBUT ---
        start = time.time()
        print(f"\n--- ⏱️ TOP CHRONO SESSION {session_id[:8]} ---")

        transcript = ""
        for i, m in enumerate(messages):
            role = "User" if m.get("prompt") else "Assistant"
            cont = m.get("prompt") if role == "User" else m.get("reponse")
            transcript += f"--- MESSAGE {i + 1} ({role}) ---\n{cont}\n\n"

        # --- ASTUCE AFFICHAGE : On définit les backticks dans une variable ---
        CODE_BLOCK = "```"

        # --- PROMPT UTILISATEUR INTÉGRÉ ---
        consigne_systeme = f"""Tu es un Moteur de Consolidation Mémoire.
Tâche : Analyse cette session COMPLÈTE et génère une fiche de résumé pour CHAQUE message.
Ta mission est de classer CHAQUE message utilisateur selon trois axes :
1. SUJET
2. ACTION
3. CATÉGORIE
OBJECTIF CRITIQUE : MAINTIEN DE L'INTENTION
- Analyse le contexte global pour déterminer le SUJET RÉEL de la session.
- Exemple : Si l'utilisateur dit "Bonjour" puis "Corrige ce script python", le "Bonjour" doit être classé SCRIPT/CODER (car c'est le but de la session), pas GENERAL/PARLER.

RÈGLES DE CLASSIFICATION :
1. SUJET (Choisir un seul parmi : [{", ".join([e.value for e in Sujet])}])
1) Script
   - Toute demande qui concerne du code Python, une fonction, un bug, un snippet.
   - Contient du code, parle d'un script, de logique Python, d'un agent écrit en code.
   → SUJET = Script

2) Fichier
   - Toute demande qui concerne un fichier NON-PYTHON : .md, .json, .yaml, .txt, config.
   - Toute demande qui modifie, lit, crée, restructure un fichier.
   → SUJET = Fichier

3) SecondMind
   - Toute demande qui concerne mon système IA, les agents, la structure, les dossiers, les règles, ou la gouvernance.
   - Toute discussion portant sur la logique interne, la mémoire, les pipelines, les intentions.
   - Si le message parle de Semi d’une manière générale et n’est pas un fichier ni un script, c’est SECONDMIND.

6) Setup
   - Installation, drivers, Windows, configuration PC, problèmes système, matériel informatique

9) General
   - Sujet sur la vie personnelle de Maxime ou Sujet indéfini, aucun domaine clair. À utiliser SEULEMENT si le sujet n'est pas en lien avec l'écosystème Secondmind.

2. ACTION (Choisir une seule parmi : [{", ".join([e.value for e in Action])}])
   ⚠️ RÈGLE : Si SUJET = SCRIPT, FICHIER ou SECONDMIND -> ACTION NE PEUT PAS ÊTRE 'PARLER'.
1) Parler
   - Questions, discussions, messages émotionnels, conversation normale.

2) Penser
   - Analyse, réflexion, définition, compréhension, hypothèses.

3) Faire
   - Action concrète : créer, corriger, configurer, organiser, modifier.

4) Coder
   - Toute demande directe d’écriture ou modification de code.

5) Debug
   - Toute demande de correction, identification ou résolution de bug dans du code.

3. CATÉGORIE (Choisir une seule parmi : [{", ".join([e.value for e in Categorie])}])
    - Planifier
    - Tester
    - Configurer
    - Documenter
    - Analyser
    - Definir
    - Comparer
    - Demander
    - Confirmer
    - Saluer

### CATÉGORIES pour CODER
    Agent #si le script est un agent
    Backend #si le script est mon backend
    Systeme #tout autre script qui n'est ni un agent ni mon backend
    Test
    Autre

FORMAT DE SORTIE (Répéter ce bloc pour chaque message) :
=== MSG 1 ===
{CODE_BLOCK}json
{{
 "sujet": "...",
 "action": "...",
 "categorie": "...",
 "resume": "Synthèse télégraphique du contenu"
}}
{CODE_BLOCK}
IMPORTANT : Une fois tous les messages traités, écris EXPLICITEMENT : "=== FIN DE SESSION ===" et arrête-toi.
"""

        prompt_final = (
            f"<|im_start|>system\n{consigne_systeme}<|im_end|>\n"
            f"<|im_start|>user\nVoici le transcript à analyser :\n{transcript}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )

        try:
            self.logger.info(
                f"🧠 Analyse globale session {session_id[:8]} ({len(messages)} msgs)..."
            )

            generateur = self.llm_synthese.generer_stream(prompt_final)
            full_response = ""

            print("--- 📺 DÉBUT DU STREAMING LLM ---")
            for chunk in generateur:
                token = str(chunk)
                full_response += token
                print(token, end="", flush=True)

                if "=== FIN DE SESSION ===" in full_response:
                    print("\n🛑 Stop Signal détecté.")
                    break

            full_response = full_response.split("=== FIN DE SESSION ===")[0]

            # --- PARSING JSON ROBUSTE ---
            interactions_generees = []
            blocs = re.split(r"===\s*MSG\s*\d+\s*===", full_response)

            if len(blocs) > 1:
                blocs = blocs[1:]
            nb_a_traiter = min(len(blocs), len(messages))

            for i in range(nb_a_traiter):
                bloc_texte = blocs[i].strip()
                if not bloc_texte:
                    continue

                # Extraction via JSON Parser
                try:
                    intention_obj, resume_str = self._extraire_intention_du_bloc(
                        bloc_texte
                    )
                except Exception as e:
                    self.logger.log_error(f"Erreur parsing MSG {i + 1}: {e}")
                    continue

                contexte_technique = [
                    Souvenir(
                        contenu="Batch Auto", titre="BATCH", type="systeme", score=0.0
                    )
                ]

                inter = Interaction(
                    prompt=f"Résumé {i + 1}/{len(messages)}",
                    reponse=resume_str,  # ✅ String Résumé
                    system="System Prompt Batch (Consolidation)",
                    intention=intention_obj,  # ✅ Objet Intention
                    contexte_memoire=contexte_technique,
                    meta=MetadataFichier(
                        session_id=session_id,
                        message_turn=i + 1,
                        source_agent="ProcesseurBrutePersistante",
                        type_memoire="persistante",
                        fichiers_consultes=[],
                        validation_juge=True,
                        score_qualite=1.0,
                        nb_problemes=0,
                        details_juge="Généré par Consolidation Batch",
                        len_contenu=len(resume_str),
                        ref_vectoriel=None,
                        ref_whoosh=None,
                        data_libre={"source": "consolidation_globale"},
                    ),
                )
                # 🛡️👁️‍🗨️🛡️# VALIDATION FORMAT SORTIE
                # On valide chaque item généré par le batch
                self.auditor.valider_format_sortie(inter)

                interactions_generees.append(inter)

            print(f"⏱️ Temps écoulé : {time.time() - start:.2f}s")
            return interactions_generees

        except Exception as e:
            self.logger.log_error(f"Erreur LLM Batch: {e}")
            return None

    def _extraire_intention_du_bloc(self, texte: str) -> Tuple[ResultatIntention, str]:
        """
        Parser robuste pour convertir la sortie textuelle du LLM en objets typés.

        Gère les irrégularités du JSON généré par le LLM (virgules traînantes,
        guillemets manquants) et effectue un mapping "Fuzzy" vers les Enums
        du système (Sujet, Action, Catégorie) pour garantir la conformité des données.

        Args:
            texte (str): Fragment de texte contenant le JSON d'un message.

        Returns:
            Tuple[ResultatIntention, str]: L'objet intention validé et le résumé textuel.
        """
        # 1. Extraction JSON (inchangé)
        start = texte.find("{")
        end = texte.rfind("}")
        if start == -1 or end == -1:
            raise ValueError(f"Pas de JSON trouvé : {texte[:50]}...")
        json_str = texte[start : end + 1]

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            json_str = re.sub(r",\s*}", "}", json_str)
            try:
                data = json.loads(json_str)
            except:
                raise ValueError(f"JSON invalide: {json_str[:50]}...")

        # 2. Nettoyage Strings
        def clean(val):
            if not val:
                return "GENERAL"  # Fallback safe
            return str(val).strip().upper()

        s_raw = clean(data.get("sujet"))
        a_raw = clean(data.get("action"))
        c_raw = clean(data.get("categorie"))
        resume = data.get("resume", "Pas de résumé fourni.")

        # 3. MAPPING STRICT VERS ENUMS (Patch Robustesse)
        def safe_enum(enum_class, value, default):
            """Tente conversion exacte -> insensible casse -> défaut"""
            try:
                # 1. Essai direct (Valeur exacte)
                return enum_class(value)
            except ValueError:
                # 2. Tentative insensible à la casse
                s_val = str(value).lower().strip()
                for member in enum_class:
                    if member.value.lower() == s_val:
                        return member
                # 3. Fallback
                return default

        # Définition des valeurs par défaut (Premier élément de l'Enum par sécurité)
        def_s = list(Sujet)[0]
        def_a = list(Action)[0]
        def_c = list(Categorie)[0]

        # Application du patch sur les variables brutes (s_raw, a_raw, c_raw)
        s_final = safe_enum(Sujet, s_raw, def_s)
        a_final = safe_enum(Action, a_raw, def_a)
        c_final = safe_enum(Categorie, c_raw, def_c)

        return ResultatIntention(
            prompt="Classification Batch",
            sujet=s_final,
            action=a_final,
            categorie=c_final,
        ), resume

    def _sauvegarder_resume(self, interaction: Interaction, data_brute: Dict) -> Path:
        """
        Sérialisation canonique du souvenir consolidé.

        Génère un nom de fichier sémantiquement riche (Sujet_Action_Date_Hash)
        permettant une identification rapide sans lecture du contenu.
        Force la conversion des Enums en chaînes de caractères pour une compatibilité JSON totale.

        Returns:
            Path: Chemin absolu du fichier sauvegardé.
        """

        # 1. Extraction des valeurs String pour le nom de fichier
        # On utilise getattr pour être robuste si c'est déjà un string ou un Enum
        def get_val(obj):
            return obj.value if hasattr(obj, "value") else str(obj)

        s = get_val(interaction.intention.sujet).replace(" ", "")
        a = get_val(interaction.intention.action).replace(" ", "")
        c = get_val(interaction.intention.categorie).replace(" ", "")

        ts_orig = data_brute.get("timestamp") or datetime.now().isoformat()
        try:
            date_str = datetime.fromisoformat(str(ts_orig)).strftime("%Y%m%d_%H%M%S")
        except Exception:
            date_str = datetime.now().strftime("%Y%m%d_%H%M%S")

        h = hashlib.md5(interaction.reponse.encode()).hexdigest()[:4]
        nom = f"{s}_{a}_{c}_{date_str}_{h}.json"

        chemin = self.persistante_dir / nom

        # 2. Conversion manuelle en Dict pour éviter le bug JSON {} des Enums
        data_dict = asdict(interaction)

        # On force la conversion des Enums en string dans le dictionnaire final
        if "intention" in data_dict:
            data_dict["intention"]["sujet"] = s
            data_dict["intention"]["action"] = a
            data_dict["intention"]["categorie"] = c

        with open(chemin, "w", encoding="utf-8") as f:
            # On dump le dictionnaire nettoyé, pas l'objet brut
            json.dump(data_dict, f, ensure_ascii=False, indent=2, cls=CustomJSONEncoder)

        return chemin

    def _indexer_resume(self, interaction: Interaction, chemin: Path):
        """
        Ancrage sémantique final du souvenir.

        Synchronise les deux moteurs de recherche :
        1. **Moteur Vectoriel** : Ajout de l'embedding du résumé pour le RAG conceptuel.
        2. **Agent Recherche (Whoosh)** : Indexation des mots-clés et des métadonnées
           (Sujet/Action) pour le filtrage explicite.
        """

        def get_val(obj):
            return obj.value if hasattr(obj, "value") else str(obj)

        s_val = get_val(interaction.intention.sujet)
        a_val = get_val(interaction.intention.action)
        c_val = get_val(interaction.intention.categorie)

        meta = {
            "fichier": str(chemin),
            "session_id": interaction.meta.session_id,
            "tag_sujet": s_val,
            "tag_action": a_val,
            "tag_categorie": c_val,
            "type": "resume_batch",
        }

        self.moteur_vectoriel.ajouter_fragment(interaction.reponse, meta=meta)

        self.agent_recherche.update_index(
            nouveau_fichier=str(chemin),
            type_memoire="persistante",
            sujet=s_val,
            action=a_val,
            categorie=c_val,
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("🚀 TEST MANUEL : Mode Session Globale.")
    proc = ProcesseurBrutePersistante()
    proc.delai_timeout_heures = 0
    proc.traiter_batch_differe()
