#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AgentContexte - Gestionnaire Intelligent du Contexte Conversationnel
Module de gestion et d'orchestration du contexte mémoire pour le système multi-agents.
L'AgentContexte récupère, filtre et organise les informations pertinentes provenant de
trois sources principales : règles symboliques, recherche sémantique et mémoire RAG.
Classes:
    AgentContexte: Agent responsable de la récupération et du filtrage du contexte.
Responsabilités principales:
    1. Orchestration des agents AgentRecherche et AgentJuge
    2. Gestion des règles symboliques (matching exact via regex)
    3. Détection des catégories et tags contextuels
    4. Recherche sémantique des règles pertinentes
    5. Filtrage et re-ranking des souvenirs via scoring
    6. Gestion de l'historique conversationnel
    7. Garantie de non-vacuité des contextes (fallbacks systématiques)
    8. Dédoublonnage des éléments contextuels
Flux de traitement (Pipeline):
    1. Chargement de la configuration YAML spécifique
    2. Détection des règles symboliques (exact matching)
    3. Détection des catégories via triggers
    4. Injection des règles de vérité suprême ("truth")
    5. Recherche sémantique des règles (top-k)
    6. Récupération des READMEs pertinents
    7. Évaluation et classement des souvenirs RAG
    8. Dédoublonnage et protection contre les contextes vides
    9. Validation du format de sortie
Contrats d'Interface:
    Entrées:
        - ResultatIntention: Analyse d'intention du prompt utilisateur
        - ResultatRecherche: Souvenirs bruts candidats du RAG
    Sortie:
        - ResultatContexte: Contexte agrégé et organisé
Configuration (YAML):
    - regles_symboliques: Mapping regex -> IDs de règles
    - triggers_categories: Mapping tags -> regex patterns
    - seuil_pertinence_juge: Score minimum pour accepter un souvenir
    - max_elements_contexte: Nombre max de souvenirs à retourner
    - max_historique_session: Limite de taille de l'historique
    - tags_prioritaires: Tags à charger en priorité
    - fichier_protocole_alerte: Nom du fichier protocole d'intervention
    - Dédoublonnage basé sur les titres pour éviter les doublons
    - Fallbacks systématiques pour chaque catégorie (règles, docs, mémoire)
    - Validation stricte du format de sortie via l'auditor
    - Délégation des accès disque à AgentRecherche (propriétaire I/O)
    - Support de continuité conversationnelle via historique persistant
"""

import re
import json
import os
import yaml
from pathlib import Path
from typing import Dict, List
from agentique.base.META_agent import AgentBase
from agentique.base.contrats_interface import (
    ResultatContexte,
    ResultatRecherche,
    ResultatIntention,
    Souvenir,
    Regle,
    DocumentationTechnique,
    FichierReadme,
)
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentique.sous_agents_gouvernes.agent_Recherche.agent_Recherche import (
        AgentRecherche,
    )
    from agentique.sous_agents_gouvernes.agent_Juge.agent_Juge import AgentJuge


class AgentContexte(AgentBase):
    """
    Gère la récupération et le filtrage du contexte mémoire.
    Orchestre AgentRecherche et formate les résultats.
    """

    def __init__(self, agent_recherche: "AgentRecherche", agent_juge: "AgentJuge"):
        super().__init__(nom_agent="AgentContexte")

        if agent_recherche is None:
            raise RuntimeError("❌ agent_recherche obligatoire")
        if agent_juge is None:
            raise RuntimeError("❌ agent_juge obligatoire")

        self.agent_recherche = agent_recherche
        self.agent_juge = agent_juge

        # 1. CHARGEMENT DE LA CONFIG (YAML)
        self.config = self._charger_config()

        # 2. CHARGEMENT DES LOGIQUES DEPUIS LE YAML
        # Logique A : IDs Précis (ex: "analogie" -> "R_010")
        self.regles_symboliques_map = self.config.get("regles_symboliques", {})

        # Logique B : Tags Catégories (ex: "sys" -> "R_001", "R_004"...)
        self.triggers_categories = self.config.get("triggers_categories", {})

        self.historique_conversation: List[str] = []

        self.logger.info(
            f"✅ AgentContexte chargé. (IDs: {len(self.regles_symboliques_map)}, Tags: {len(self.triggers_categories)})"
        )

    # =========================================================================
    # 1. CHARGEMENT FICHIER CONFIG
    # =========================================================================
    def _charger_config(self) -> Dict:
        """Charge la configuration YAML spécifique de l'AgentContexte."""
        file_path = self.auditor.get_path("config")

        if not file_path:
            raise RuntimeError(
                "❌ Erreur critique : Impossible de récupérer le chemin 'config' depuis l'Auditor."
            )

        p = Path(file_path)

        if not p.exists():
            raise FileNotFoundError(f"❌ Configuration critique manquante : {p}")

        with open(p, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        return data.get("configuration", {})

    # =========================================================================
    # 🚨 GOUVERNANCE : Accès et mise à jour de l'historique de chat (synchrone)
    # =========================================================================
    def get_historique_chat(self) -> List[str]:
        """Retourne l'historique conversationnel stocké par l'AgentContexte."""
        return self.historique_conversation

    def mettre_a_jour_historique(self, prompt: str, reponse: str):
        """Ajoute et tronque selon la config YAML stricte."""
        self.historique_conversation.append(prompt)
        self.historique_conversation.append(reponse)
        limit = self.config.get("max_historique_session")
        if limit and len(self.historique_conversation) > limit:
            self.historique_conversation = self.historique_conversation[-limit:]

    def get_historique_nouveau_chat(self, limit: int = 10) -> List[str]:
        """
        Charge l'historique récent pour initier la continuité.
        Délègue l'accès disque à l'AgentRecherche (Propriétaire I/O).
        """
        self.logger.info("🔄 Chargement continuité (via AgentRecherche)...")

        if not self.agent_recherche:
            self.logger.log_warning(
                "⚠️ AgentRecherche non disponible pour charger l'historique."
            )
            return []

        # Délégation stricte
        historique = self.agent_recherche.recuperer_historique_brut(limit=limit)

        self.logger.info(f"✅ {len(historique)} messages chargés en mémoire vive.")
        return historique

    # =========================================================================
    # 🧠 2. COEUR DU SYSTÈME : LE TRI (PIPELINE)
    # =========================================================================
    def recuperer_contexte_intelligent(
        self,
        resultat_intention: ResultatIntention,
        resultat_recherche: ResultatRecherche,
    ) -> ResultatContexte:
        """ "
        Récupère et organise intelligemment le contexte pour une requête utilisateur.
        Cette méthode orchesthe trois sources de contexte :
        1. **Règles Symboliques** : Règles déclenchées par mots-clés explicites du prompt
        2. **Règles Sémantiques** : Règles correspondant sémantiquement au prompt via recherche vectorielle
        3. **Documentation & Mémoire** : READMEs et souvenirs (RAG) filtrés par pertinence
        Processus :
        - Détecte et charge les règles symboliques (exact matching via regex)
        - Détecte et charge les règles par tags/catégories (triggers_categories du YAML)
        - Charge les règles de vérité suprême ("truth")
        - Recherche sémantiquement les règles pertinentes (Top 3)
        - Récupère les READMEs associés au contexte
        - Évalue et classe les souvenirs RAG par pertinence (via agent_juge)
        - Applique dédoublonnage pour éviter les doublons
        - Garantit la non-vacuité avec fallbacks pour chaque catégorie
        Args:
            resultat_intention (ResultatIntention): Résultat de l'analyse d'intention contenant le prompt et le sujet détecté
            resultat_recherche (ResultatRecherche): Résultat de la recherche brute contenant les souvenirs candidats
        Returns:
            ResultatContexte: Objet agrégé contenant :
                - regles_actives : Liste des Regle sélectionnées (symboliques + sémantiques + thruth)
                - fichiers_readme : Liste des FichierReadme pertinents
                - contexte_memoire : Liste des Souvenir filtrés et classés par score
                - historique : Historique récent de la conversation
                - intention_detectee : Intention analysée du prompt
        Notes:
            - Dédoublonnage basé sur titre pour éviter les doublons
            - Seuils configurables: seuil_pertinence_juge, max_elements_contexte
            - Fallbacks systématiques si aucun résultat (Règle/Doc/Mémoire par défaut)
            - Validation du format de sortie via auditor
        """
        prompt = resultat_intention.prompt
        souvenirs_bruts = resultat_recherche.souvenirs_bruts

        self.logger.info(f"Tri intelligent de {len(souvenirs_bruts)} souvenirs...")

        # 1. INITIALISATION DES LISTES TYPÉES
        regles_actives: List[Regle] = []
        docs_actives: List[FichierReadme] = []
        contexte_evalue: List[Souvenir] = []

        # Set pour dédoublonnage
        ids_deja_charges = set()

        # ---------------------------------------------------------
        # A. RÈGLES SYMBOLIQUES
        # ---------------------------------------------------------
        # On demande explicitement à l'agent recherche de récupérer le contenu de ces IDs
        ids_cibles = self.associer_regles_symboliques(prompt)
        if ids_cibles:
            for rid in ids_cibles:
                found = self.agent_recherche.rechercher_regles(rid)
                for r in found:
                    if r.titre not in ids_deja_charges:
                        regles_actives.append(r)
                        ids_deja_charges.add(r.titre)
        # ---------------------------------------------------------
        # B. LOGIQUE GLOBALE (Tags via triggers_categories)
        # ---------------------------------------------------------
        # Récupère les Tags définis dans le YAML (ex: 'sys', 'doc')
        tags_detectes = self._detecter_tags_categories(prompt)

        if tags_detectes:
            for tag in tags_detectes:
                found = self.agent_recherche.rechercher_regles(tag)
                for r in found:
                    if r.titre not in ids_deja_charges:
                        regles_actives.append(r)
                        ids_deja_charges.add(r.titre)
        # ---  RÈGLES "TRUTH" (Vérité Suprême) ---
        regles_truth = self.agent_recherche.rechercher_regles("truth")
        for r in regles_truth:
            if r.titre not in ids_deja_charges:
                regles_actives.append(r)
                ids_deja_charges.add(r.titre)

        # Protection Règles vides
        if not regles_actives:
            r_base = Regle(
                contenu="Agis comme un assistant utile et inoffensif.",
                titre="DEFAULT_BASE",
                type="regle",
                score=1.0,
            )
            regles_actives.append(r_base)

        # =========================================================
        # B.2 LOGIQUE SÉMANTIQUE (MOTEUR LÉGISLATIF V3)
        # =========================================================
        # C'est ici qu'on applique le Protocole Alerte :
        # On cherche des règles qui "ressemblent" sémantiquement au problème actuel.
        try:
            # On cherche large (Top 3) pour ne pas rater une règle subtile
            regles_vectorielles = self.agent_recherche.rechercher_regles_semantiques(
                prompt, top_k=3
            )

            if regles_vectorielles:
                self.logger.info(
                    f"⚖️ {len(regles_vectorielles)} règles sémantiques injectées."
                )

            for r in regles_vectorielles:
                # Dédoublonnage basé sur le contenu (car le titre peut varier)
                # Ou on utilise le titre si on est sûr de son unicité
                if r.titre not in ids_deja_charges:
                    regles_actives.append(r)
                    ids_deja_charges.add(r.titre)

        except Exception as e:
            self.logger.log_warning(f"⚠️ Échec injection règles sémantiques : {e}")

        # ---------------------------------------------------------
        # C. DOCUMENTATION & MÉMOIRE
        # ---------------------------------------------------------
        # Doc (READMEs)
        try:
            fichiers_readme = self.agent_recherche.rechercher_readme(prompt)
            for doc in fichiers_readme:
                if doc.titre not in ids_deja_charges:
                    docs_actives.append(doc)
                    ids_deja_charges.add(doc.titre)
        except Exception as e:
            self.logger.log_warning(f"Erreur recherche README: {e}")

        # Protection Doc vide
        if not docs_actives:
            # ✅ Utilisation de FichierReadme pour le fallback
            docs_actives.append(
                FichierReadme(
                    contenu="Aucun fichier README spécifique requis pour ce contexte.",
                    titre="DOC_NEANT",
                    chemin="N/A",
                    type="readme",
                    score=0.0,
                )
            )
        # Mémoire (RAG)- FILTRAGE & RE-RANKING
        # Récupération du seuil depuis le YAML
        seuil_ref = self.config.get("seuil_pertinence_juge", 0.0)
        limit_ctx = self.config.get("max_elements_contexte", 5)

        # Chargement des règles prioritaires (ex: truth) via YAML
        tags_prioritaires = self.config.get("tags_prioritaires", [])
        for tag in tags_prioritaires:
            found = self.agent_recherche.rechercher_regles(tag)

        for item in souvenirs_bruts:
            if item.type == "regle":
                # Si le RAG ramène une règle, on la classe correctement
                r_obj = Regle(
                    contenu=item.contenu,
                    titre=item.titre,
                    type="regle",
                    score=item.score,
                )
                if r_obj.titre not in ids_deja_charges:
                    regles_actives.append(r_obj)
                    ids_deja_charges.add(r_obj.titre)
                continue

            # Évaluation Juge
            item.score = self.agent_juge.calculer_pertinence_semantique(
                prompt,
                item.contenu,
                item.titre,
                [{"sujet": resultat_intention.sujet.value}],
            )
            contexte_evalue.append(item)

        contexte_evalue.sort(key=lambda x: x.score, reverse=True)
        contexte_utile = [
            s for s in contexte_evalue[:limit_ctx] if s.score >= seuil_ref
        ]

        if not contexte_utile:
            # On vérifie si l'import est là, sinon on l'ajoute en haut du fichier
            # from agentique.base.contrats_interface import Souvenir

            self.logger.info(
                "⚠️ Contexte mémoire vide -> Injection Souvenir Neutre (Fallback)."
            )
            contexte_utile.append(
                Souvenir(
                    contenu="Aucun souvenir pertinent trouvé en mémoire pour cette requête. ",
                    titre="MEMOIRE_VIDE",
                    type="info_systeme",  # Type neutre
                    score=0.1,  # Score plancher
                )
            )

        # 🚨 GARANTIE DE NON-VACUITÉ AVEC MESSAGE EXPLICITE
        # --- A. PROTECTION RÈGLES ---
        if not regles_actives:
            self.logger.info("⚠️ Aucune règle trouvée -> Injection Règle Par Défaut")
            regles_actives.append(
                Regle(
                    contenu="Respecte les directives de l'utilisateur et sois utile.",
                    titre="REGLE_DEFAULT_FALLBACK",
                    type="regle",
                    score=1.0,
                )
            )

        # --- B. PROTECTION README (Renommé & Obligation de Contenu) ---
        if not docs_actives:
            self.logger.info("⚠️ Aucun README trouvé -> Injection Doc Par Défaut")
            docs_actives.append(
                FichierReadme(
                    contenu="Aucun fichier README spécifique requis pour ce contexte.",
                    titre="README_NEANT",
                    chemin="N/A",
                    type="readme",
                    score=0.0,
                )
            )

        # --- C. PROTECTION MÉMOIRE ---
        if not contexte_utile:
            self.logger.info("⚠️ Contexte mémoire vide -> Injection Souvenir Vide")
            contexte_utile.append(
                Souvenir(
                    contenu="Aucun souvenir pertinent trouvé en mémoire pour cette requête.",
                    titre="MEMOIRE_VIDE",
                    type="info_systeme",
                    score=0.0,
                )
            )

        resultat = ResultatContexte(
            historique=self.get_historique_chat(),
            contexte_memoire=contexte_utile,
            regles_actives=regles_actives,
            fichiers_readme=docs_actives,
            intention_detectee=resultat_intention,
        )
        # 🛡️👁️‍🗨️🛡️# VALIDATION FORMAT SORTIE
        self.auditor.valider_format_sortie(resultat)

        return resultat

    # =========================================================================
    # 🧠 3. UTILITAIRES (Règles Symboliques)
    # =========================================================================

    def associer_regles_symboliques(self, prompt: str) -> List[str]:
        """
        Logique A : Cherche les mots-clés du prompt dans la map 'regles_symboliques'.
        Retourne une liste d'IDs (ex: ['R_010', 'R_011']).
        """
        prompt_lower = prompt.lower()
        ids_trouves = set()

        # self.regles_symboliques_map vient directement du YAML
        for regex_keywords, rule_ids_str in self.regles_symboliques_map.items():
            if re.search(regex_keywords, prompt_lower):
                # On gère le cas où le YAML contient "R_001, R_002"
                ids = [rid.strip() for rid in rule_ids_str.split(",") if rid.strip()]
                ids_trouves.update(ids)

        return list(ids_trouves)

    def _detecter_tags_categories(self, prompt: str) -> List[str]:
        """
        Logique B : Cherche les regex du prompt dans 'triggers_categories'.
        Retourne une liste de tags (ex: ['sys', 'doc']).
        """
        prompt_lower = prompt.lower()
        tags_trouves = set()

        # self.triggers_categories vient directement du YAML
        for tag, regex_str in self.triggers_categories.items():
            if re.search(regex_str, prompt_lower):
                tags_trouves.add(tag)

        return list(tags_trouves)

    # ----------------------------------------------------------
    # Méthodes protocole ALERTE!
    # ----------------------------------------------------------
    def recuperer_protocole_alerte(self) -> str:
        """
        Gouvernance : Récupère le contenu du fichier protocole_intervention_ALERTE.md.
        """
        try:
            # On reconstruit le chemin via l'auditor pour être robuste
            chemin_regles = self.auditor.get_path("regles")
            if not chemin_regles:
                return "ERREUR: Chemin 'regles' introuvable."

            nom_fichier = self.config.get(
                "fichier_protocole_alerte", "protocole_intervention_ALERTE.md"
            )
            fichier_protocole = Path(chemin_regles) / nom_fichier

            if fichier_protocole.exists():
                return fichier_protocole.read_text(encoding="utf-8")

            return (
                f"ERREUR CRITIQUE : Fichier protocole introuvable à {fichier_protocole}"
            )

        except Exception as e:
            self.logger.log_error(f"Erreur lecture protocole alerte : {e}")
            return "ERREUR CRITIQUE : Lecture protocole impossible."

    def get_historique_recent(self, limit: int = 10) -> List[str]:
        """Retourne les N derniers messages de l'historique RAM."""
        # self.historique_conversation est une liste [User, AI, User, AI...]
        if not self.historique_conversation:
            return []
        # On prend les 'limit' derniers éléments
        return self.historique_conversation[-limit:]
