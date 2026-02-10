#!/usr/bin/env python3
"""
AgentRecherche - Moteur de Récupération d'Information Multi-Modale
Module central responsable de l'accès unifié aux données du système (RAG, Fichiers, Web).

Ce module implémente une architecture de recherche hybride combinant :
1.  **Recherche Symbolique (Keyword-based) :** Via 'Everything' (système de fichiers) et 'Whoosh' (indexation inversée) pour une précision chirurgicale.
2.  **Recherche Sémantique (Vector-based) :** Via FAISS (délégué à AgentMemoire) pour la récupération contextuelle par similarité.
3.  **Recherche Externe :** Interface avec le Web pour l'acquisition de connaissances en temps réel.

Responsabilités Architecturales :
    - Abstraction de la complexité I/O pour les autres agents.
    - Stratégie de "Re-ranking" et de "Boosting" basée sur l'intention utilisateur.
    - Mécanisme de "Context Swapping" : Remplace dynamiquement un log brut par son résumé consolidé pour économiser la fenêtre de contexte.
    - Maintenance asynchrone des index (consistance éventuelle).
"""

import re
import threading
import os
import json
import csv
import subprocess
from pathlib import Path
from typing import List, Dict, Optional, Any, Set
import time
from datetime import datetime, timedelta
from collections import defaultdict

import yaml

from agentique.base.META_agent import AgentBase
from agentique.base.contrats_interface import (
    Sujet,
    Action,
    Categorie,
    CustomJSONEncoder,
    ResultatRechercheMemoire,
    Souvenir,
    ResultatIntention,
    Regle,
    FichierReadme,
    DocumentationTechnique,
    ContenuFichierBrut,
    RatioQualite
)  # <--- MODIF IMPORT
from agentique.sous_agents_gouvernes.agent_Recherche.recherche_memoire import (
    RechercheMemoireTool,
)
from agentique.sous_agents_gouvernes.agent_Recherche.recherche_web import RechercheWeb

try:
    from whoosh.index import create_in, open_dir, exists_in
    from whoosh.fields import Schema, TEXT, ID, DATETIME, NUMERIC
    from whoosh.qparser import MultifieldParser, OrGroup

    # Suppression de StandardAnalyzer, ajout de FancyAnalyzer (ou RegexTokenizer)
    from whoosh.analysis import LowercaseFilter, RegexTokenizer
except ImportError as e:
    raise RuntimeError(f"❌ ERREUR: {e}")


class AgentRecherche(AgentBase):
    """
    Passerelle unifiée d'accès au savoir et à la mémoire du système.

    Cette classe orchestre les différents moteurs de recherche (texte, vecteur, fichier)
    et applique des logiques de filtrage avancées avant de retourner des objets 'Souvenir'
    standardisés. Elle agit comme le "Bibliothécaire" du système multi-agents.

    Attributes:
        chemin_executable_everything (str): Chemin vers l'outil 'es.exe' pour l'indexation OS ultra-rapide.
        chemin_index_whoosh (Path): Localisation de l'index inversé persisté.
        outil_web (RechercheWeb): Module autonome pour les requêtes internet profondes.
    """

    def __init__(self):
        super().__init__(nom_agent="AgentRecherche")

        # 1. CHARGEMENT CONFIGURATION UNIQUE
        self.config_data = self._charger_config_yaml()
        self.configuration = self.config_data.get("configuration", {})

        # 2. Inventaire Physique basé sur Configuration
        self.liste_types_memoire = self.configuration.get("memoire", {}).get("type_memoire", [])

        for type_memoire in self.liste_types_memoire:
            chemin_absolu = self.auditor.get_path(type_memoire)
            if chemin_absolu and Path(chemin_absolu).exists():
                self.liste_types_memoire.append(type_memoire)

        # 3. Chemins Absolus
        self.chemin_racine_memoire = Path(self.auditor.get_path("memoire"))
        self.chemin_index_whoosh = Path(self.auditor.get_path("woosh_index"))

        # 4. Outil Everything (Configurable)
        self.chemin_executable_everything = self._trouver_everything_strict()
        self.logger.info(
            f"✅ Everything verrouillé: {self.chemin_executable_everything}"
        )

        # 5. Initialisation Moteur Textuel
        self._garantir_existence_index_whoosh()

        # 6. Outil Interne (Interface LLM)
        self.outiluration_memoire = RechercheMemoireTool(self)

        # 7. Injection de Dépendances (initialisées à None, injectées par agent_Semi)
        self.agent_memoire = None
        self.moteur_vectoriel = None
        # RechercheWeb nécessite un MoteurLLM, injecté plus tard par agent_Semi
        # via: self.agenturation.outil_web = RechercheWeb(self.moteur_llm)
        self.outil_web = None

    def _charger_config_yaml(self) -> Dict:
        path_conf_str = self.auditor.get_path("config")

        if not path_conf_str:
            raise RuntimeError(
                "❌ Configuration introuvable : L'Auditor n'a pas renvoyé de chemin pour 'config'."
            )

        path_conf = Path(path_conf_str)
        if not path_conf.exists():
            raise RuntimeError(
                f"❌ Fichier 'configuration.yaml' introuvable à l'adresse : {path_conf}"
            )

        with open(path_conf, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _trouver_everything_strict(self) -> str:
        # --- CORRECTION ---
        # 1. Priorité absolue : Config YAML
        path_config = self.configuration.get("everything_exe_path")
        if path_config and os.path.exists(path_config):
            return path_config
        # ------------------

        # 2. Fallback (tes chemins habituels)
        possibles = [r"D:\DevToolz\es.exe", "es.exe"]
        for path in possibles:
            try:
                subprocess.run([path, "-h"], capture_output=True, timeout=2)
                return path
            except Exception:
                continue
        raise RuntimeError("❌ CRITIQUE : Everything (es.exe) introuvable.")

    def _garantir_existence_index_whoosh(self):
        """Vérifie ou crée l'index Whoosh"""
        if not exists_in(str(self.chemin_index_whoosh)):
            self._creer_schema_whoosh()

    def _creer_schema_whoosh(self):
        # On définit un analyseur "brut" : il coupe par mots mais ne supprime RIEN
        # Le RegexTokenizer(expression=r'\w+') capture tout ce qui ressemble à un mot/chiffre
        analyser_brut = RegexTokenizer() | LowercaseFilter()

        schema = Schema(
            path=ID(stored=True, unique=True),
            filename=TEXT(stored=True),
            # On applique l'analyseur brut ici pour ne plus ignorer "mention" ou "mémoire"
            content=TEXT(analyzer=analyser_brut, stored=True),
            type_memoire=ID(stored=True),
            timestamp=DATETIME(stored=True),
            sujet_tag=ID(stored=True),
            action_tag=ID(stored=True),
            categorie_tag=ID(stored=True),
            session_id=ID(stored=True),
            message_turn=NUMERIC(stored=True),
        )
        os.makedirs(self.chemin_index_whoosh, exist_ok=True)
        create_in(str(self.chemin_index_whoosh), schema)
        self.logger.info("Index Whoosh initialisé.")

    # =========================================================================
    # 🌍 RECHERCHE WEB
    # =========================================================================

    def recherche_web_profonde(self, objectif: str) -> str:
        if self.outil_web:
            # On injecte la config Web fraîche du YAML si l'outil supporte la reconfig
            # ou on suppose que l'outil lit la même source.
            return self.outil_web.executeruration_profonde(objectif)
        return "❌ Erreur : Outil 'RechercheWeb' non disponible."

    # =========================================================================
    # 🔧 MOTEUR TECHNIQUE (Privé - Utilisé par toutes les fonctions physiques)
    # =========================================================================

    def _executer_everything(self, query: Any, limit: int = 20) -> List[str]:
        if limit is None:
            limit = self.configuration.get("limites", {}).get(
                "recherche_everything_max", 20
            )

        # 1) Normalisation
        if isinstance(query, list):
            args_query = query
        else:
            import shlex

            try:
                args_query = shlex.split(str(query), posix=False)
            except Exception:
                args_query = str(query).split()

        # 1.1) Harden tokens
        args_query = [str(x) for x in args_query if x is not None and str(x).strip()]

        # 1.2) Fix path:"...\"
        fixed = []
        for t in args_query:
            if t.startswith('path:"') and t.endswith('\\"'):
                t = t[:-2] + '"'
            fixed.append(t)
        args_query = fixed

        # 2) Commande (options AVANT requête)
        cmd = [self.chemin_executable_everything, "-n", str(limit)] + args_query
        self.logger.info(f"🚀 CMD: {cmd}")

        # 3) Exécution
        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                creationflags=0x08000000,
            )
            if res.stderr:
                self.logger.log_warning(f"⚠️ Everything stderr: {res.stderr}")
            if res.returncode != 0:
                self.logger.log_error(f"❌ Everything exit code: {res.returncode}")
                return []
        except Exception as e:
            self.logger.log_error(f"Erreur appel subprocess: {e}")
            return []

        # 4) Résultat
        out = (res.stdout or "").strip()
        if not out:
            return []
        return [l.strip() for l in out.splitlines() if l.strip()]

    # =========================================================================
    # 🔍 1. RECHERCHE RÈGLES
    # =========================================================================

    def rechercher_regles(self, tag: str) -> List[Regle]:
        """
        Récupère les règles de gouvernance via un filtrage symbolique strict (Tags).
        Retourne une liste brute d'atomes Regle.
        """

        # 1. Récupération du chemin via Auditor
        chemin_regles = self.auditor.get_path("regles", nom_agent="memoire")
        if not chemin_regles:
            return []

        # 2. Gestion intelligente des guillemets (Correctif Everything)
        chemin_str = str(chemin_regles)
        base_query = f'path:"{chemin_str}"' if " " in chemin_str else f'path:{chemin_str}'

        query = f'{base_query} *{tag}*.json'
        chemins_fichiers = self._executer_everything(query)

        atomes_regles: List[Regle] = []

        for chemin in chemins_fichiers:
            try:
                path_obj = Path(chemin)
                contenu_json = path_obj.read_text(encoding="utf-8")

                # --- DÉCODAGE JSON ROBUSTE ---
                try:
                    data = json.loads(contenu_json)
                    texte_regle = data.get("regle", contenu_json)
                except json.JSONDecodeError:
                    texte_regle = contenu_json

                # --- CRÉATION DE L'ATOME ---
                regle = Regle(
                    contenu=texte_regle,
                    titre=path_obj.stem,
                    type="regle",
                    score=10.0
                )
                atomes_regles.append(regle)

            except Exception as e:
                self.logger.log_warning(f"⚠️ Règle ignorée car illisible : {chemin}. {e}")
                continue

        # 🛡️👁️‍🗨️🛡️ VALIDATION PAR L'AUDITOR
        self.auditor.valider_format_sortie(atomes_regles)

        return atomes_regles
    # =========================================================================
    # 🔍 RECHERCHE 1.5 : RÈGLES SÉMANTIQUES (MOTEUR LÉGISLATIF DÉDIÉ)
    # =========================================================================
    def rechercher_regles_semantiques(self, query: str, top_k: int = 3) -> List[Regle]:
        """
        Interroge le "Moteur Législatif" pour trouver des règles conceptuellement liées au prompt.

        Contrairement à la recherche par tag, cette méthode utilise des embeddings vectoriels
        pour identifier l'esprit de la loi plutôt que la lettre. Elle permet d'appliquer
        des contraintes pertinentes même si l'utilisateur n'utilise pas les mots-clés exacts.

        Args:
            query (str): Le contexte ou la demande de l'utilisateur.
            top_k (int): Nombre de règles les plus pertinentes à retourner.

        Returns:
            List[Regle]: Règles triées par similarité cosinus.
        """

        # Sécurité : Vérifier que le moteur existe (il est optionnel dans AgentMemoire)
        if (
            not self.agent_memoire
            or not hasattr(self.agent_memoire, "moteur_regles")
            or not self.agent_memoire.moteur_regles
        ):
            return []

        try:
            # 1. Recherche Vectorielle Pure
            resultats_bruts = self.agent_memoire.moteur_regles.rechercher(
                query, top_k=top_k
            )

            regles_trouvees = []
            for item in resultats_bruts:
                meta = item.get("meta", {})
                score = item.get("score", 0.0)

                # 2. Conversion en objet Regle standardisé
                # On utilise 'contenu' ou 'regle' selon ce qui a été stocké par Reflexor
                contenu_txt = meta.get("regle") or meta.get("contenu") or "Règle vide"
                titre = meta.get("trigger") or "REGLE_SEMANTIQUE"

                # On force le type pour l'affichage dans Parole
                regles_trouvees.append(
                    Regle(
                        contenu=contenu_txt,
                        titre=f"{titre} (Sim: {score:.2f})",
                        type="regle_vectorielle",
                        score=score,
                    )
                )

            return regles_trouvees

        except Exception as e:
            self.logger.log_error(f"Erreur recherche règles sémantiques : {e}")
            return []

    # =========================================================================
    # 🔍 RECHERCHE 2 : LES README
    # =========================================================================

    def _norm_tokens(self, s: str) -> set[str]:
        s = s.strip()
        s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)
        s = s.lower()
        s = s.replace("_", " ").replace("-", " ")
        s = re.sub(r"\s+", " ", s).strip()
        return set(re.findall(r"[a-z0-9]+", s))

    # ✅ CORRECTION : Ajout de self
    def _key_tokens_from_readme(self, filename: str) -> set[str]:
        name = filename.strip()
        if not name.lower().startswith("readme_") or not name.lower().endswith(".md"):
            return set()

        base = name[:-3][7:]
        base = base.replace("_", " ").replace("-", " ")
        base = re.sub(r"\s+", " ", base).strip().lower()
        return set(re.findall(r"[a-z0-9]+", base))

    def rechercher_readme(self, prompt: str) -> List[FichierReadme]:
        """
        Mission : Trouver et lire les fichiers README pertinents.
        Retourne une liste brute d'atomes FichierReadme (validée par l'Auditor).
        """

        # 1. Récupération du chemin via Auditor
        chemin_connaissances = self.auditor.get_path("connaissances")
        if not chemin_connaissances:
             return []

        # 2. Gestion intelligente des guillemets (Correctif Everything)
        chemin_str = str(chemin_connaissances)
        base_query = f'path:"{chemin_str}"' if " " in chemin_str else f'path:{chemin_str}'

        query = f'{base_query} README_*.md'
        chemins_trouves = self._executer_everything(query)

        if not chemins_trouves:
            self.logger.log_warning(f"⚠️ Aucun README trouvé dans: {chemin_connaissances}")
            return []

        # 3. Préparation du filtrage intelligent
        prompt_tokens = self._norm_tokens(prompt)
        atomes_readme: List[FichierReadme] = []

        for chemin in chemins_trouves:
            try:
                path_obj = Path(chemin)
                nom = path_obj.name

                # --- FILTRAGE PAR TOKENS ---
                key_tokens = self._key_tokens_from_readme(nom)
                if key_tokens and not key_tokens.issubset(prompt_tokens):
                    continue

                # --- CRÉATION DE L'ATOME ---
                contenu = path_obj.read_text(encoding="utf-8")
                atome = FichierReadme(
                    contenu=contenu,
                    titre=path_obj.name,
                    chemin=str(path_obj),
                    type="readme",
                    score=10.0
                )
                atomes_readme.append(atome)

            except Exception as e:
                self.logger.log_warning(f"⚠️ Erreur lecture README {chemin}: {e}")
                continue

        # 🛡️👁️‍🗨️🛡️ VALIDATION PAR L'AUDITOR (Accepte maintenant la liste d'atomes)
        self.auditor.valider_format_sortie(atomes_readme)

        return atomes_readme

    # =========================================================================
    # 🔍 RECHERCHE 3 : DOCUMENTATION TECHNIQUE (Manuels / PDF / Specs)
    # =========================================================================

    def rechercher_documentation_technique(self, motif: str) -> List[DocumentationTechnique]:
        """
        Mission : Trouver des manuels techniques dans le sous-dossier dédié.
        Retourne une liste brute d'atomes DocumentationTechnique.
        """

        # 1. Sécurisation du Path via Auditor
        chemin_connaissances = self.auditor.get_path("connaissances")
        if not chemin_connaissances:
            return []

        dossier_tech = Path(chemin_connaissances) / "documentation_technique"
        if not dossier_tech.exists():
            self.logger.log_warning(f"⚠️ Dossier technique absent: {dossier_tech}")
            return []

        # 2. Gestion intelligente des guillemets (Correctif Everything)
        chemin_str = str(dossier_tech)
        base_query = f'path:"{chemin_str}"' if " " in chemin_str else f'path:{chemin_str}'
        query = f'{base_query} *{motif}*'

        # 3. Exécution
        chemins_trouves = self._executer_everything(query)
        atomes_doc = []

        for f_path in chemins_trouves:
            path_obj = Path(f_path)
            try:
                contenu = path_obj.read_text(encoding="utf-8", errors="replace")
                atomes_doc.append(DocumentationTechnique(
                    contenu=contenu,
                    titre=path_obj.name,
                    source_url="",
                    type="doc_technique",
                    score=10.0,
                ))
            except Exception as e:
                self.logger.log_warning(f"⚠️ Doc illisible {f_path}: {e}")
                continue

        # 🛡️👁️‍🗨️🛡️ VALIDATION PAR L'AUDITOR
        self.auditor.valider_format_sortie(atomes_doc)

        return atomes_doc
    # =========================================================================
    # 🔍 RECHERCHE 4 : CONTEXTE VECTORIEL (SOUVENIRS + SWAP + BOOSTING)
    # =========================================================================

    def recherche_contexte_memoire_vectorielle(
        self, query: str, intention: Optional[ResultatIntention] = None
    ) -> ResultatRechercheMemoire: # ✅ Changement du type de retour
        """
        Exécute le pipeline RAG principal avec optimisation contextuelle.
        Retourne un objet ResultatRechercheMemoire standardisé.
        """
        t_start = time.time() # ⏱️ Début chrono

        # Config Limits
        top_final = self.configuration.get("limites", {}).get("resultats_finaux", 10)
        boost_factor = self.configuration.get("scoring", {}).get("boost_intention", 0.5)

        # 1. Dépendances (FAIL FAST)
        if not self.agent_memoire or not self.agent_memoire.moteur_vectoriel:
            raise RuntimeError("❌ AgentRecherche : Moteur vectoriel non disponible.")

        chemin_persistante = self.auditor.get_path("persistante")
        if not chemin_persistante:
            raise RuntimeError("❌ AgentRecherche : Chemin 'persistante' introuvable.")

        # 2. Exécution Vectorielle
        try:
            resultats_bruts = self.agent_memoire.moteur_vectoriel.rechercher(
                query, top_k=15
            )
        except Exception as e:
            raise RuntimeError(f"❌ Erreur technique Moteur Vectoriel : {e}")

        souvenirs_candidats = []

        # 3. Traitement : Swap & Scoring
        for item in resultats_bruts:
            meta = item.get("meta", {})
            score_vectoriel = float(item.get("score", 0.0))
            path_original = meta.get("fichier", "")

            contenu_final = meta.get("contenu", "") or "ERREUR_CONTENU_VIDE"
            titre_final = Path(path_original).name if path_original else "Souvenir_Vectoriel"
            type_final = meta.get("type", "vectoriel")

            # --- LOGIQUE DE SWAP ---
            session_id = meta.get("session_id")
            turn = meta.get("message_turn")

            if session_id and turn and "historique" in str(path_original):
                resume_trouve = self._tenter_recuperation_resume(
                    session_id, turn, str(chemin_persistante)
                )
                if resume_trouve:
                    contenu_final = resume_trouve.contenu
                    titre_final = resume_trouve.titre
                    type_final = "resume_consolide"

            souvenirs_candidats.append(Souvenir(
                contenu=contenu_final,
                titre=titre_final,
                type=type_final,
                score=score_vectoriel,
            ))

        # 4. Boosting Intention
        if intention:
            termes = {
                intention.sujet.value.lower(),
                intention.action.value.lower(),
                intention.categorie.value.lower(),
            }
            termes.discard("inconnu")
            termes.discard("general")

            for s in souvenirs_candidats:
                matches = sum(1 for terme in termes if terme in s.titre.lower())
                if matches > 0:
                    s.score = s.score * (1.0 + (boost_factor * matches))

        # 5. Tri et Tronquage
        souvenirs_candidats.sort(key=lambda x: x.score, reverse=True)
        selection_finale = souvenirs_candidats[:top_final]

        # ✅ 6. Encapsulation (Correction du contrat)
        resultat_final = ResultatRechercheMemoire(
            souvenirs_bruts=selection_finale,
            nb_fichiers_scannes=len(resultats_bruts),
            tempsuration=time.time() - t_start
        )

        # 🛡️👁️‍🗨️🛡️ VALIDATION PAR L'AUDITOR
        # On valide l'objet final, pas la liste
        self.auditor.valider_format_sortie(resultat_final)

        return resultat_final
    # =========================================================================
    # 🔍 RECHERCHE 5 : HISTORIQUE DE CONVERSATION
    # =========================================================================

    def recuperer_historique_brut(self, limit: int = 10) -> List[str]:
        """
        Accède directement à la chronologie brute des interactions (Short-Term Memory).

        Cette méthode contourne les index sémantiques pour fournir une continuité
        conversationnelle immédiate ("Ce qui vient juste de se passer").
        Essentiel pour maintenir le fil de la discussion dans la fenêtre de contexte active.

        Args:
            limit (int): Nombre de derniers échanges (tours de parole) à récupérer.

        Returns:
            List[str]: Liste alternée [Prompt, Réponse, Prompt, ...].
        """
        historique_recent = []
        try:
            chemin_historique = self.auditor.get_path("historique")
            if not chemin_historique:
                return []

            p = Path(chemin_historique)
            if not p.exists():
                return []

            # 1. Lister et trier par modification (plus récent à la fin)
            fichiers = sorted(list(p.glob("interaction_*.json")), key=os.path.getmtime)

            # 2. Prendre les N derniers
            fichiers_recents = fichiers[-limit:]

            for f_path in fichiers_recents:
                try:
                    with open(f_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        # Extraction robuste User/Assistant
                        p_user = data.get("prompt", "")
                        r_assistant = data.get("reponse", "")

                        if p_user:
                            historique_recent.append(p_user)
                        if r_assistant:
                            historique_recent.append(r_assistant)

                except Exception as e:
                    self.logger.log_warning(
                        f"Fichier historique corrompu ignoré {f_path.name}: {e}"
                    )
                    continue

            return historique_recent

        except Exception as e:
            self.logger.log_error(f"Erreur lecture historique brut: {e}")
            return []

    # =========================================================================
    # 🛠️ HELPER SWAP (Utilisé par recherche_historique)
    # =========================================================================

    def _swapper_vers_resume(
        self, original_path: Path, session_id: str, turn: int
    ) -> Souvenir:
        """
        Logique de Fallback :
        1. Tente de trouver le résumé via _tenter_recuperation_resume.
        2. Si trouvé -> Retourne le Résumé.
        3. Si non trouvé -> Lit le fichier original et le retourne.
        """
        chemin_persistante = self.auditor.get_path("persistante")

        # 1. Tentative de Swap (On réutilise la logique existante)
        if chemin_persistante:
            resume = self._tenter_recuperation_resume(
                session_id, turn, chemin_persistante
            )
            if resume:
                return resume

        # 2. Fallback : Lecture de l'original (Si pas de swap possible)
        try:
            # Utilisation de la méthode safe interne ou lecture directe
            if hasattr(self, "_lire_fichier_safe"):
                contenu_original = self._lire_fichier_safe(original_path)
            else:
                contenu_original = original_path.read_text(
                    encoding="utf-8", errors="replace"
                )

            return Souvenir(
                contenu=contenu_original,
                titre=original_path.name,
                type="historique_recent",
                score=1.0,
            )
        except Exception as e:
            self.logger.log_warning(
                f"⚠️ Impossible de lire l'original pour fallback {original_path}: {e}"
            )
            return Souvenir(
                contenu="", titre=original_path.name, type="erreur_lecture", score=0.0
            )

    # Méthodes helpers nécessaires pour que le code ci-dessus fonctionne (non modifiées mais requises)
    def _lire_fichier_safe(self, chemin: Path) -> str:
        if not chemin.exists():
            raise FileNotFoundError(f"❌ {chemin}")
        return chemin.read_text(encoding="utf-8", errors="replace")

    def _tenter_recuperation_resume(
        self, session_id: str, turn: int, chemin_persistante: str
    ) -> Optional[Souvenir]:
        """
        Cherche dans 'persistante' un fichier qui contient le bon SessionID et Turn.
        Utilise Everything 'content:' pour une précision chirurgicale.
        """
        # Query Everything : path:"..." content:"session_id"
        chemin_str = str(chemin_persistante)
        if " " in chemin_str:
            base_query = f'path:"{chemin_str}"'
        else:
            base_query = f'path:{chemin_str}'  # ⚠️ PAS de guillemets ici

        # Query Everything : path:... content:"session_id"
        query = f'{base_query} content:"{session_id}"'
        try:
            candidats = self._executer_everything(
                query, limit=5
            )  # 5 est une constante technique acceptable ici (low level)
            for path_str in candidats:
                path_obj = Path(path_str)
                try:
                    text = path_obj.read_text(encoding="utf-8")
                    if session_id in text:
                        data = json.loads(text)

                        # Vérification du Tour (Match exact requis)
                        # On gère les deux formats de stockage possibles
                        meta_turn = data.get("meta", {}).get("message_turn")
                        if meta_turn is None:
                            meta_turn = data.get("message_turn")

                        if str(meta_turn) == str(turn):
                            # MATCH CONFIRMÉ
                            return Souvenir(
                                contenu=data.get("reponse", "")
                                or data.get("resume", ""),
                                titre=path_obj.name,
                                type="resume",
                                score=1.0,
                            )
                except:
                    continue
        except Exception:
            return None  # Fail Safe : Pas de swap

        return None

    # =========================================================================
    # 🔍 RECHERCHE 5 : HISTORIQUE CHRONOLOGIQUE (TIMELINE + SWAP)
    # =========================================================================

    def recherche_historique(self, limit: int = None) -> List[Souvenir]:
        """
        Récupère les dernières interactions de l'historique.
        Retourne une liste brute d'atomes Souvenir (validée par l'Auditor).
        """
        if limit is None:
            limit = self.confuration.get("limites", {}).get("historique_recent", 5)


        # 1. Accès au chemin via Auditor
        chemin_historique = self.auditor.get_path("historique", nom_agent="memoire")
        if not chemin_historique:
            raise RuntimeError("❌ AgentRecherche : Chemin 'historique' introuvable.")

        dossier_hist = Path(chemin_historique)
        if not dossier_hist.exists():
            return []

        # 2. Collecte des fichiers (triés par date de modification décroissante)
        fichiers = sorted(
            dossier_hist.glob("interaction_*.json"),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )

        selection = fichiers[:limit]
        souvenirs_reconstruits: List[Souvenir] = []

        # 3. Reconstitution des atomes avec Context Swapping
        for f_path in selection:
            try:
                content = self._lire_fichier_safe(f_path)
                data = json.loads(content)
                meta = data.get("meta", {})

                sid = meta.get("session_id") or data.get("session_id")
                turn = meta.get("message_turn") or data.get("message_turn")

                if sid and turn:
                    # Utilise le résumé consolidé si disponible (Swapping)
                    souvenir = self._swapper_vers_resume(f_path, sid, turn)
                    souvenirs_reconstruits.append(souvenir)
                else:
                    # Fallback sur le brut
                    souvenirs_reconstruits.append(
                        Souvenir(
                            contenu=content,
                            titre=f_path.name,
                            type="historique_recent",
                            score=1.0,
                        )
                    )
            except Exception as e:
                self.logger.log_warning(f"Erreur lecture historique {f_path.name}: {e}")
                continue

        # 4. Remise dans l'ordre chronologique (du plus vieux au plus récent pour le contexte)
        souvenirs_reconstruits.reverse()

        # 🛡️👁️‍🗨️🛡️ VALIDATION PAR L'AUDITOR
        self.auditor.valider_format_sortie(souvenirs_reconstruits)

        return souvenirs_reconstruits

    # =========================================================================
    # 🔍 RECHERCHE 6 : VERBATIM (CITATIONS EXACTES)
    # =========================================================================

    def recuperer_resume_par_session(self, session_id: str, turn: int) -> List[Souvenir]:
        """
        Recherche une interaction précise pour le Context Swapping.
        Retourne une liste brute d'atomes Souvenir.
        """
        chemin_persistante = self.auditor.get_path("persistante", nom_agent="memoire")
        if not chemin_persistante:
            return []

        # Utilisation de la logique de récupération robuste
        souvenir = self._tenter_recuperation_resume(session_id, turn, str(chemin_persistante))

        # Retourne une liste (même si un seul élément) pour la cohérence Auditor
        resultat = [souvenir] if souvenir else []

        self.auditor.valider_format_sortie(resultat)
        return resultat

    def _extraire_tout_le_texte(self, data):
        """Exploration récursive pour indexer 100% du contenu JSON."""
        texte = []
        if isinstance(data, dict):
            for k, v in data.items():
                # On ignore les IDs techniques pour ne pas polluer l'index
                if k in ["id", "session_id", "ref_vectoriel"]:
                    continue
                texte.append(self._extraire_tout_le_texte(v))
        elif isinstance(data, list):
            for item in data:
                texte.append(self._extraire_tout_le_texte(item))
        else:
            texte.append(str(data))
        return " ".join(texte)

    # =========================================================================
    # 🔍 RECHERCHE 7 : FICHIERS PROJET HORS MÉMOIRE (CODE & CONFIG)
    # =========================================================================

    def recherche_fichier_hors_memoire(self, pattern: str) -> ResultatRechercheMemoire: # <--- Changement de type ici
        """
        Permet à l'agent d'inspecter son propre code source ou sa configuration (Introspection).
        Retourne un objet standardisé ResultatRechercheMemoire.
        """
        # ... (Tout le code précédent reste identique jusqu'à la validation) ...

        # 1. Racine Projet
        root_dir = self.auditor.recuperer_racine_projet()
        if not root_dir:
            raise RuntimeError("❌ AgentRecherche : Racine du projet introuvable via Auditor.")
        # Gestion intelligente des guillemets (Correctif Everything)
        root_str = str(root_dir)
        base_path = f'path:"{root_str}"' if " " in root_str else f'path:{root_str}'

        # 2. Construction de la requête
        query = (
            f'{base_path} {pattern} '
            f'(ext:py|ext:yaml|ext:json|ext:md|path:.github) '
            f'!path:logs !path:backups !path:__pycache__ !.env'
        )

        candidats_bruts = self._executer_everything(query, limit=20)
        atomes_souvenirs: List[Souvenir] = []

        # 3. Filtrage et Lecture
        for chemin in candidats_bruts:
            path_obj = Path(chemin)
            nom = path_obj.name.lower()
            path_str = str(path_obj).lower()

            # --- A. REFUS IMMÉDIAT (Blacklist) ---
            if any(x in path_str for x in ["backup", "logs", "__pycache__"]):
                continue
            if ".env" in nom or nom.endswith(".bak") or " - copie" in nom:
                continue

            # --- B. VALIDATION (Whitelist) ---
            is_valid_ext = any(nom.endswith(ext) for ext in [".py", ".yaml", ".yml", ".json", ".md"])
            is_github = ".github" in path_str

            if not (is_valid_ext or is_github):
                continue

            # --- C. LECTURE & ATOMISATION ---
            try:
                contenu = self._lire_fichier_safe(path_obj)

                atome = Souvenir(
                    contenu=contenu,
                    titre=path_obj.name,
                    type="fichier_code",
                    score=10.0
                )
                atomes_souvenirs.append(atome)
            except Exception as e:
                self.logger.log_warning(f"⚠️ Fichier projet illisible {path_obj.name}: {e}")
                continue

# 🛡️👁️‍🗨️🛡️ VALIDATION PAR L'AUDITOR
        # On ne valide plus la liste, mais on construit l'objet final

        resultat_final = ResultatRechercheMemoire(
            souvenirs_bruts=atomes_souvenirs,
            nb_fichiers_scannes=len(candidats_bruts),
            tempsuration=0.0 # Optionnel
        )

        self.auditor.valider_format_sortie(resultat_final)

        return resultat_final
    def uration_whoosh_targeted(
        self, query_text: str, fichiers_candidats: List[str] = None, limit: int = 10
    ) -> List[Souvenir]:
        """
        Effectue la recherche Whoosh et convertit les résultats en Souvenirs.
        Accepte maintenant un argument 'limit' pour le RRF.
        """
        souvenirs = []
        try:
            ix = open_dir(str(self.chemin_index_whoosh))
            with ix.searcher() as searcher:
                # Utilisation simple du parseur
                parser = MultifieldParser(
                    ["content", "filename"], ix.schema, group=OrGroup
                )
                whoosh_query = parser.parse(query_text)

                # Recherche avec la limite dynamique
                results = searcher.search(whoosh_query, limit=limit)

                for hit in results:
                    path = hit.get("path", "")

                    # Filtrage post-search si Everything a donné des candidats
                    if fichiers_candidats and path not in fichiers_candidats:
                        continue  # Skip ce résultat

                    # ✅ CONVERSION EN SOUVENIR
                    contenu_brut = hit.get("content", "")
                    if len(contenu_brut) > 800:
                        contenu_brut = contenu_brut[:800] + "..."

                    souvenirs.append(
                        Souvenir(
                            contenu=contenu_brut,
                            titre=hit.get("filename", "Inconnu"),
                            type=hit.get("type_memoire", "persistante"),
                            score=hit.score,
                        )
                    )

        except Exception as e:
            self.logger.log_error(f"Erreur Whoosh Targeted: {e}")

        return souvenirs

    # =========================================================================
    # 🔍 RECHERCHE VERBATIM (Citations Exactes via Whoosh)
    # =========================================================================

    def rechercher_citation_exacte(self, phrase_exacte: str) -> List[Souvenir]:
        """
        Recherche une citation EXACTE dans l'historique complet.

        Pipeline :
        1. Everything : Trouve tous les fichiers historique_*.json
        2. Whoosh : Cherche la phrase dans le contenu
        3. Validation disque : Vérifie que la citation est présente

        Args:
            phrase_exacte: La phrase exacte à retrouver (avec ponctuation)

        Returns:
            List[Souvenir] avec souvenirs contenant la citation prouvée
        """
        start_time = time.time()

        # 1. Everything : Pré-filtre sur les fichiers historique
        chemin_hist = self.auditor.get_path("historique")
        if not chemin_hist:
            self.logger.log_warning("Chemin historique introuvable pour recherche verbatim")
            return []

        chemin_str = str(chemin_hist)
        base_query = f'path:"{chemin_str}"' if " " in chemin_str else f'path:{chemin_str}'
        query_everything = f'{base_query} *.json'
        fichiers_candidats = self._executer_everything(query_everything, limit=100)

        # 2. Skip Whoosh (il tokenise la phrase), validation disque directe
        resultats_verifies = []

        # 3. Validation disque sur TOUS les fichiers candidats
        for fichier_path in fichiers_candidats:
            try:
                path_obj = Path(fichier_path)
                contenu_brut = path_obj.read_text(encoding='utf-8', errors='replace')

                # Vérification stricte : la phrase DOIT être dedans
                if phrase_exacte in contenu_brut:
                    resultats_verifies.append(Souvenir(
                        contenu=contenu_brut,
                        titre=path_obj.name,
                        type="verbatim_prouve",
                        score=10.0  # Score max : citation confirmée
                    ))
            except Exception as e:
                self.logger.log_warning(f"Erreur lecture {fichier_path}: {e}")
                continue

        elapsed = time.time() - start_time
        self.logger.info(f"Recherche verbatim: {len(resultats_verifies)} résultats en {elapsed:.2f}s")

        # Validation Auditor
        self.auditor.valider_format_sortie(resultats_verifies)

        return resultats_verifies

    # =========================================================================
    # 🔧 UTILITAIRES BAS NIVEAU
    # =========================================================================

    def _lire_fichier_safe(self, chemin: Path) -> str:
        """
        Lecture robuste : Force UTF-8.
        Si un caractère est illisible, on le remplace () pour ne pas perdre tout le contenu.
        CRASH si le fichier n'existe pas (Fail Fast sur la structure).
        """
        if not chemin.exists():
            # C'est une erreur structurelle grave si on essaie de lire un fichier fantôme
            raise FileNotFoundError(
                f"❌ Erreur Lecture : Le fichier n'existe pas physiquement : {chemin}"
            )

        try:
            # errors='replace' est un compromis acceptable ici :
            # Mieux vaut avoir 99% du texte avec un '?' que de crasher pour un emoji mal encodé.
            return chemin.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            # Si même avec replace ça plante (ex: problème de droits, disque dur), on crash.
            raise RuntimeError(f"❌ Erreur I/O Critique sur {chemin.name} : {e}")

    # =========================================================================
    # 🛠️ MÉTHODES DE MAINTENANCE (INDEXATION)
    # =========================================================================
    def update_index(
        self,
        contenu: str = None,
        type_memoire: str = "persistante",
        sujet: str = None,
        action: str = None,
        categorie: str = None,
        session_id: str = None,
        message_turn: int = None,
        nouveau_fichier: str = None,
    ):
        """
        Gère la maintenance de l'index inversé (Whoosh) pour la recherche textuelle.

        Supporte deux modes opératoires :
        1. **Mise à jour Atomique** (si `nouveau_fichier` est fourni) : Met à jour un seul document
           en temps réel après une interaction.
        2. **Reconstruction Totale** (si aucun argument) : Lance un ré-indexage complet
           en mode batch via `AsyncWriter` pour optimiser les I/O et garantir la consistance.

        Args:
            contenu (str, optional): Texte brut à indexer directement.
            nouveau_fichier (str, optional): Chemin du fichier physique à ingérer.
            [...tags metadata]: Métadonnées pour les facettes de recherche.
        """
        if not self.chemin_index_whoosh.exists():
            self._creer_schema_whoosh()

        ix = open_dir(str(self.chemin_index_whoosh))

        # =========================================================
        # CAS 1 : MISE À JOUR CIBLÉE (Fichier spécifique)
        # =========================================================
        if nouveau_fichier:
            writer = ix.writer()  # Ouverture locale
            try:
                path_f = Path(nouveau_fichier)
                final_content = contenu

                if not final_content and path_f.exists():
                    if path_f.suffix in [".json", ".jsonl"]:
                        data = json.loads(path_f.read_text(encoding="utf-8"))
                        final_content = self._extraire_tout_le_texte(data)
                    else:
                        final_content = path_f.read_text(encoding="utf-8")

                writer.update_document(
                    path=str(path_f),
                    filename=path_f.name,
                    content=final_content or "",
                    type_memoire=type_memoire,
                    timestamp=datetime.now(),
                    sujet_tag=sujet or "",
                    action_tag=action or "",
                    categorie_tag=categorie or "",
                    session_id=session_id or "",
                    message_turn=message_turn or 0,
                )
                writer.commit()
                self.logger.info(f"📝 Whoosh mis à jour : {path_f.name}")
            except Exception as e:
                writer.cancel()
                self.logger.log_error(f"❌ Erreur Cas 1 : {e}")

        # =========================================================
        # CAS 2 : RECONSTRUCTION TOTALE
        # =========================================================
        else:
            self.logger.info(
                "🔧 Maintenance : Reconstruction totale via AsyncWriter..."
            )
            count = 0

            # On utilise AsyncWriter pour éviter le verrouillage "already in a doc"
            from whoosh.writing import AsyncWriter

            writer = AsyncWriter(ix)

            types_memoire = [
                "reflexive",
                "historique",
                "persistante",
                "connaissances",
                "modules_formation",
            ]

            try:
                for type_mem in types_memoire:
                    path_str = self.auditor.get_path(type_mem)
                    if not path_str:
                        continue
                    dossier = Path(path_str)
                    if not dossier.exists():
                        continue

                    for fichier in dossier.rglob("*"):
                        if not fichier.is_file() or fichier.suffix not in [
                            ".json",
                            ".jsonl",
                            ".txt",
                            ".md",
                        ]:
                            continue
                        if any(
                            ex in str(fichier).lower()
                            for ex in ["backup", "trash", "archive", ".git"]
                        ):
                            continue

                        # --- PRÉPARATION (HORS WRITER) ---
                        try:
                            if fichier.suffix in [".json", ".jsonl"]:
                                data = json.loads(fichier.read_text(encoding="utf-8"))
                                content_val = self._extraire_tout_le_texte(data)

                                # Tags robustes
                                s_val, a_val, c_val = "", "", ""
                                cl = data.get("classification") or data.get("intention")
                                if cl:
                                    s_val = cl.get("sujet", "")
                                    a_val = cl.get("action", "")
                                    c_val = cl.get("categorie", "")
                            else:
                                content_val = fichier.read_text(
                                    encoding="utf-8", errors="replace"
                                )

                            if not content_val.strip():
                                continue

                            # --- AJOUT AU DOCUMENT ---
                            # On utilise add_document au lieu d'update pour une reconstruction
                            # C'est beaucoup plus rapide et évite les conflits de verrous
                            writer.add_document(
                                path=str(fichier),
                                filename=fichier.name,
                                content=content_val,
                                type_memoire=type_mem,
                                timestamp=datetime.fromtimestamp(
                                    fichier.stat().st_mtime
                                ),
                                sujet_tag=str(s_val),
                                action_tag=str(a_val),
                                categorie_tag=str(c_val),
                                session_id="",
                                message_turn=0,
                            )
                            count += 1

                            if count % 1000 == 0:
                                self.logger.info(
                                    f"💾 Ingestion en cours : {count} fichiers..."
                                )

                        except Exception as e_file:
                            # Ici, on log l'erreur mais le writer n'est pas bloqué
                            continue

                # Un SEUL commit à la toute fin pour tout valider
                writer.commit()
                self.logger.info(f"✅ Terminé : {count} documents indexés.")

            except Exception as e_globale:
                writer.cancel()
                self.logger.log_error(
                    f"❌ Erreur critique reconstruction : {e_globale}"
                )

    def rechercher_par_classification(
        self,
        sujet: Optional[Sujet] = None,
        action: Optional[Action] = None,
        categorie: Optional[Categorie] = None,
        tags: Optional[List[str]] = None,
        limite: int = 20,
        depuis: Optional[datetime] = None,
    ) -> List[Dict]:
        """
        Effectue une requête structurée sur les métadonnées des souvenirs (Analytics).

        Permet d'extraire des sous-ensembles de mémoire basés sur la taxonomie du système
        (Sujet, Action, Catégorie) plutôt que sur le contenu textuel. Utile pour les
        tâches de synthèse périodique ou d'analyse comportementale.

        Args:
            sujet, action, categorie (Enum): Filtres taxonomiques.
            depuis (datetime): Fenêtre temporelle d'analyse.

        Returns:
            List[Dict]: Données structurées pour analyse ou export.
        """
        self.stats_manager.incrementer_stat_specifique("recherches_semantiques", 1)

        resultats = []
        dossier_historique = Path(self.auditor.get_path("historique"))

        if not dossier_historique or not dossier_historique.exists():
            self.logger.log_warning(
                "Dossier historique non trouvé pour recherche sémantique"
            )
            return resultats

        try:
            # Parcourir tous les fichiers d'historique
            for fichier in dossier_historique.glob("**/*.json"):
                try:
                    contenu = json.loads(fichier.read_text(encoding="utf-8"))

                    # Vérifier si c'est une interaction avec classification
                    if not isinstance(contenu, dict) or "classification" not in contenu:
                        continue

                    classification = contenu["classification"]
                    timestamp_str = contenu.get("timestamp", "")

                    # Filtres de date
                    if depuis:
                        try:
                            timestamp = datetime.fromisoformat(
                                timestamp_str.replace("Z", "+00:00")
                            )
                            if timestamp < depuis:
                                continue
                        except:
                            continue

                    # Filtres sémantiques
                    correspond = True

                    if sujet and classification.get("sujet") != sujet.value:
                        correspond = False

                    if action and classification.get("action") != action.value:
                        correspond = False

                    if categorie and classification.get("categorie") != categorie.value:
                        correspond = False

                    if tags:
                        tags_interaction = classification.get("tags", [])
                        if not any(
                            tag.lower() in [t.lower() for t in tags_interaction]
                            for tag in tags
                        ):
                            correspond = False

                    if correspond:
                        resultats.append(
                            {
                                "fichier": str(fichier),
                                "timestamp": timestamp_str,
                                "prompt": contenu.get("prompt", ""),
                                "reponse": contenu.get("reponse", "") + "..."
                                if len(contenu.get("reponse", "")) > 200
                                else contenu.get("reponse", ""),
                                "classification": classification,
                                "metadata": contenu.get("metadata", {}),
                            }
                        )

                except Exception as e:
                    self.logger.log_warning(f"Erreur lecture fichier {fichier}: {e}")
                    continue

            # Trier par timestamp décroissant et limiter
            resultats.sort(key=lambda x: x["timestamp"], reverse=True)
            resultats = resultats[:limite]

            self.logger.info(
                f"Recherche sémantique: {len(resultats)} résultats trouvés"
            )
            return resultats

        except Exception as e:
            self.logger.log_error(f"Erreur dans recherche sémantique: {e}")
            return []

    def statistiques_semantiques(self, periode_jours: int = 30) -> Dict[str, Any]:
        """
        Génère des statistiques sur les interactions par classification.

        Args:
            periode_jours: Période d'analyse en jours

        Returns:
            Dictionnaire avec statistiques détaillées
        """
        depuis = datetime.now() - timedelta(days=periode_jours)

        # Récupérer toutes les interactions de la période
        toutes_interactions = self.rechercher_par_classification(
            depuis=depuis, limite=1000
        )

        if not toutes_interactions:
            return {"erreur": "Aucune interaction trouvée pour la période"}

        stats = {
            "periode": f"{periode_jours} derniers jours",
            "total_interactions": len(toutes_interactions),
            "par_sujet": {},
            "par_action": {},
            "par_categorie": {},
            "tags_frequents": {},
            "evolution_temporelle": {},
            "combinaisons_frequentes": {},
        }

        # Analyser par classification
        for interaction in toutes_interactions:
            classif = interaction["classification"]

            # Stats par sujet
            sujet = classif.get("sujet", "INCONNU")
            stats["par_sujet"][sujet] = stats["par_sujet"].get(sujet, 0) + 1

            # Stats par action
            action = classif.get("action", "INCONNUE")
            stats["par_action"][action] = stats["par_action"].get(action, 0) + 1

            # Stats par catégorie
            categorie = classif.get("categorie", "INCONNUE")
            stats["par_categorie"][categorie] = (
                stats["par_categorie"].get(categorie, 0) + 1
            )

            # Tags fréquents
            for tag in classif.get("tags", []):
                stats["tags_frequents"][tag] = stats["tags_frequents"].get(tag, 0) + 1

            # Combinaisons fréquentes
            combo = f"{sujet}/{action}/{categorie}"
            stats["combinaisons_frequentes"][combo] = (
                stats["combinaisons_frequentes"].get(combo, 0) + 1
            )

        # Trier les résultats par fréquence
        for cle in [
            "par_sujet",
            "par_action",
            "par_categorie",
            "tags_frequents",
            "combinaisons_frequentes",
        ]:
            stats[cle] = dict(
                sorted(stats[cle].items(), key=lambda x: x[1], reverse=True)
            )

        self.logger.info(
            f"Statistiques sémantiques générées pour {len(toutes_interactions)} interactions"
        )
        return stats

    def exporter_donnees_semantiques(self, format_export: str = "json") -> str:
        """
        Exporte toutes les données de classification pour analyse externe.

        Args:
            format_export: "json" ou "csv"

        Returns:
            Chemin du fichier exporté
        """
        try:
            # Récupérer toutes les interactions
            toutes_interactions = self.rechercher_par_classification(limite=10000)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            if format_export == "json":
                nom_fichier = f"export_semantique_{timestamp}.json"
                chemin_persistante = self.auditor.get_path("persistante")
                if not chemin_persistante:
                    self.logger.log_error("Chemin persistante introuvable pour export")
                    return ""

                chemin_export = Path(chemin_persistante) / nom_fichier

                donnees_export = {
                    "timestamp_export": datetime.now().isoformat(),
                    "total_interactions": len(toutes_interactions),
                    "interactions": toutes_interactions,
                }

                with open(chemin_export, "w", encoding="utf-8") as f:
                    json.dump(
                        donnees_export,
                        f,
                        ensure_ascii=False,
                        indent=2,
                        cls=CustomJSONEncoder,
                    )

            elif format_export == "csv":
                nom_fichier = f"export_semantique_{timestamp}.csv"
                chemin_persistante = self.auditor.get_path("persistante")
                if not chemin_persistante:
                    self.logger.log_error("Chemin persistante introuvable pour export")
                    return ""

                chemin_export = Path(chemin_persistante) / nom_fichier

                with open(chemin_export, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(
                        [
                            "timestamp",
                            "sujet",
                            "action",
                            "categorie",
                            "tags",
                            "prompt_extrait",
                            "reponse_extrait",
                        ]
                    )

                    for interaction in toutes_interactions:
                        classif = interaction["classification"]
                        writer.writerow(
                            [
                                interaction["timestamp"],
                                classif.get("sujet", ""),
                                classif.get("action", ""),
                                classif.get("categorie", ""),
                                ";".join(classif.get("tags", [])),
                                interaction["prompt"][:100],
                                interaction["reponse"][:100],
                            ]
                        )

            self.logger.info(f"Export sémantique créé: {chemin_export}")
            return str(chemin_export)

        except Exception as e:
            self.logger.log_error(f"Erreur lors de l'export sémantique: {e}")
            return ""

    # =========================================================================
    # RECHERCHE FUNCTION TOOL MEMORY_SEARCH
    # =========================================================================

    # =========================================================================
    # 🔧 UTILITAIRE PUBLIC (Utilisé par RechercheMemoireTool)
    # =========================================================================

    def localiser_fichiers_physiques(self, pattern: str) -> List[str]:
        root_path = self.auditor.recuperer_racine_projet()
        if not root_path:
            raise RuntimeError("❌ AgentRecherche : Racine projet introuvable.")

        # Conversion backslash Windows
        root_str = str(root_path).replace("/", "\\")
        pattern_clean = pattern.replace('"', "").replace("'", "").strip()

        # ✅ CORRECTIF : Pas de guillemets si pas d'espace dans le path
        if " " in root_str:
            base_query = f'path:"{root_str}"'
        else:
            base_query = f"path:{root_str}"  # ← SANS guillemets

        # CONSTRUCTION DE LA STRING (et non une liste)
        # On fusionne la base et le pattern avec un espace
        query = f"{base_query} {pattern_clean}"

        # On envoie une string unique, comme dans les autres méthodes
        candidats_bruts = self._executer_everything(query, limit=20)

        chemins_valides = []
        exclusions = [".git", "venv", "__pycache__", "node_modules", "site-packages"]

        for chemin in candidats_bruts:
            try:
                path_obj = Path(chemin).resolve()
                # Vérification de sécurité : doit être dans le projet
                # (Peut lever ValueError si le chemin est hors du root)
                try:
                    path_obj.relative_to(root_path.resolve())
                except ValueError:
                    continue

                path_str_lower = str(path_obj).lower()
                if any(ex in path_str_lower for ex in exclusions):
                    continue

                chemins_valides.append(str(path_obj))
            except Exception:
                continue

        if not chemins_valides:
            self.logger.log_warning(
                f"⚠️ Aucun fichier physique trouvé pour : {pattern_clean}"
            )

        return chemins_valides

    def get_stats(self) -> Dict:
        """Retourne les statistiques de l'index"""
        try:
            ix = open_dir(str(self.chemin_index_whoosh))
            with ix.searcher() as searcher:
                doc_count = searcher.doc_count()

            return {
                "documents_indexes": doc_count,
                # Correction ici :
                "everything_disponible": self.chemin_executable_everything is not None,
                "chemin_index_whoosh": str(self.chemin_index_whoosh),
            }
        except:
            return {"error": "Impossible de lire l'index"}
