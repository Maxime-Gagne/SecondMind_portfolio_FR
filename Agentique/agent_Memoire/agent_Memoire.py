#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AgentMemoire - Gestionnaire de Persistance et d'Ancrage Cognitif
Module responsable de l'écriture, de la sauvegarde et de l'indexation de toutes les données du système.

Ce module implémente une stratégie de persistance en couches (Layered Persistence Strategy) :
1.  **Couche Brute (Safety Layer) :** Journalisation append-only (JSONL) pour garantir qu'aucune donnée n'est perdue en cas de crash.
2.  **Couche Transactionnelle (Short-Term) :** Fichiers JSON individuels représentant l'état immédiat de la conversation.
3.  **Couche Sémantique (Long-Term) :** Vectorisation des interactions pour le RAG (Narratif) et des règles (Législatif).
4.  **Couche Indexée (Search) :** Mise à jour temps réel de l'index inversé (Whoosh) pour la recherche par mots-clés.

Architecture "Twin-Engine" :
    L'agent gère deux moteurs vectoriels distincts :
    - **Moteur Narratif :** Pour les souvenirs et l'historique (RAG classique).
    - **Moteur Législatif :** Index dédié exclusivement aux règles et lois, garantissant que la gouvernance ne se dilue pas dans la narration.
"""

import json
import os
from pathlib import Path
import yaml
from datetime import datetime
from dataclasses import asdict, is_dataclass
from typing import Dict, Any, List, Optional, Union, TYPE_CHECKING
from agentique.base.META_agent import AgentBase
from agentique.base.contrats_interface import (
    CustomJSONEncoder,
    Interaction,
    ArtefactCode,
    AnalyseContenu,
)
from agentique.sous_agents_gouvernes.agent_Memoire.moteur_vecteur import MoteurVectoriel

# ✅ AJOUT : Imports conditionnels pour l'Intellisense
if TYPE_CHECKING:
    from agentique.sous_agents_gouvernes.agent_Recherche.agent_Recherche import (
        AgentRecherche,
    )
    from agentique.sous_agents_gouvernes.agent_Memoire.moteur_vecteur import (
        MoteurVectoriel,
    )


class AgentMemoire(AgentBase):
    def __init__(
        self,
        agent_recherche: "AgentRecherche",  # ✅ Typage explicite
        moteur_vectoriel: Optional["MoteurVectoriel"] = None,  # ✅ Typage explicite
        root_dir: str = None,
        session_id: str = None,
    ):
        super().__init__(nom_agent="AgentMemoire")
        """
        Contrôleur central des opérations d'écriture (I/O Write).

        Contrairement à l'AgentRecherche (Lecture), l'AgentMemoire est le seul autorisé à modifier
        l'état permanent du système. Il assure la cohérence des données entre le disque physique,
        la base vectorielle (FAISS) et le moteur de recherche (Whoosh).

        Attributes:
            moteur_vectoriel (MoteurVectoriel): Base de données des souvenirs narratifs.
            moteur_regles (MoteurVectoriel): Base de données dédiée aux règles de gouvernance.
            agent_recherche (AgentRecherche): Dépendance injectée pour la mise à jour des index de recherche.
        """

        # --- Chargement de la configuration ---
        config_path_str = self.auditor.get_path("config")
        if config_path_str and Path(config_path_str).exists():
            with open(config_path_str, "r", encoding="utf-8") as f:
                config_brute = yaml.safe_load(f)
            self.config = config_brute.get("configuration", {})
        else:
            self.config = {}

        # --- Initialisation des mémoires actives (Lecture YAML) ---
        chemins_memoire_a_chercher = self.config.get("types_memoire_actives", [])
        if "reflexive" in chemins_memoire_a_chercher:
            chemins_memoire_a_chercher.remove("reflexive")
            chemins_memoire_a_chercher.insert(0, "reflexive")

        if agent_recherche is None:
            raise RuntimeError(
                "❌ ERREUR CRITIQUE: agent_recherche est obligatoire pour AgentMemoire"
            )
        self.agent_recherche = agent_recherche

        # 1. MOTEUR NARRATIF (Souvenirs)
        self.moteur_vectoriel = moteur_vectoriel
        # 2. ✅ MOTEUR LÉGISLATIF (Règles - Nouveau Index DÉDIÉ)
        # On calcule le chemin : memoire/regles/vecteurs
        path_regles = self.auditor.get_path("regles")
        if path_regles:
            path_index_regles = os.path.join(path_regles, "vecteurs")
            self.logger.info(
                f"⚖️ Initialisation Moteur Vectoriel LÉGISLATIF : {path_index_regles}"
            )
            self.moteur_regles = MoteurVectoriel(chemin_index=path_index_regles)
        else:
            self.logger.log_warning(
                "⚠️ Chemin 'regles' introuvable. Le moteur législatif est désactivé."
            )
            self.moteur_regles = None

    # ================================================================
    # 1. SAUVEGARDE BRUTE (BACKUP SÉCURITÉ)
    # ================================================================
    def sauvegarder_interaction_brute(
        self,
        donnee_entree: Union[Interaction, str],  # Accepte Objet OU String (Role)
        contenu: str = None,
        session_id: str = None,
        message_turn: int = None,
        metadata: Dict = None,
    ) -> bool:
        """
        Exécute une journalisation de type "Write-Ahead Log" (WAL) pour la sécurité des données.

        Cette méthode est critique : elle capture l'interaction brute avant tout traitement complexe.
        Elle utilise un mode "Append-Only" avec `os.fsync` pour garantir l'atomicité et la durabilité
        de l'écriture, même en cas d'arrêt brutal du système.

        Polymorphisme :
            Accepte soit un objet `Interaction` structuré, soit des données brutes (str),
            assurant la rétrocompatibilité et la flexibilité des logs.

        Returns:
            bool: True si l'écriture physique est confirmée.
        """
        try:
            # 1. Récupérer le dossier d’écriture
            dossier_path = self.auditor.get_path("brute")
            if not dossier_path:
                return False
            dossier = Path(dossier_path)
            if not dossier.exists():
                dossier.mkdir(parents=True, exist_ok=True)

            # 2. Nom du fichier journalier
            date_str = datetime.now().strftime("%Y-%m-%d")
            log_path = dossier / f"interactions_{date_str}.jsonl"

            # 3. Préparer les données à sauvegarder
            data_to_save = {}

            # CAS A : On a reçu un objet Interaction complet (Nouveau standard)
            if is_dataclass(donnee_entree):
                data_to_save = asdict(donnee_entree)
                # On ajoute un timestamp de log si pas présent
                if "timestamp_log" not in data_to_save:
                    data_to_save["timestamp_log"] = datetime.now().isoformat()

            # CAS B : On a reçu des arguments séparés (Ancien standard / Fallback)
            elif isinstance(donnee_entree, str) and contenu is not None:
                data_to_save = {
                    "timestamp": datetime.now(),
                    "role": donnee_entree,  # Ici donnee_entree est le role
                    "contenu": contenu,
                    "session_id": session_id,
                    "message_turn": message_turn,
                    "metadata": metadata or {},
                }
            else:
                self.logger.log_warning(f"Format brute inconnu: {type(donnee_entree)}")
                return False

            # 4. Écriture Append (Atomicité via os.fsync)
            with open(log_path, "a", encoding="utf-8") as f:
                json_line = json.dumps(
                    data_to_save, ensure_ascii=False, cls=CustomJSONEncoder
                )
                f.write(json_line + "\n")
                f.flush()
                os.fsync(f.fileno())

            self.logger.log_thought(f"🔒 Backup brut sécurisé : {log_path.name}")
            return True

        except Exception as e:
            self.logger.log_error(f"❌ Erreur sauvegarde brute: {e}")
            return False

    # ================================================================
    # 2. MÉMORISATION ACTIVE (HISTORIQUE + RAG)
    # ================================================================
    def memoriser_interaction(self, interaction_element: Interaction) -> bool:
        """
        Orchestre le pipeline d'ingestion complet d'une interaction (Hot Path).

        Processus en 4 étapes synchrones :
        1. **Persistance Disque** : Écriture d'un fichier JSON atomique dans 'historique/'.
        2. **Validation** : Vérification stricte du schéma de données via Auditor.
        3. **Vectorisation** : Injection immédiate dans le Moteur Narratif pour disponibilité RAG instantanée.
        4. **Indexation** : Mise à jour de l'index Whoosh pour la recherche par mots-clés.

        Cette méthode transforme une "pensée vive" en "souvenir accessible".

        Args:
            interaction_element (Interaction): L'échange complet (Prompt + Réponse + Métadonnées).

        Returns:
            bool: Succès global de la chaîne de mémorisation.
        """
        try:
            # --- 1. Préparation du nom de fichier ---
            ts = interaction_element.meta.timestamp
            timestamp_clean = ts.replace(":", "").replace("-", "").replace(".", "")

            # Extraction sécurisée des tags (via Intention)
            if interaction_element.intention:
                sujet_val = interaction_element.intention.sujet.value
                action_val = interaction_element.intention.action.value
                categorie_val = interaction_element.intention.categorie.value
            else:
                sujet_val = "inconnu"
                action_val = "inconnue"
                categorie_val = "inconnue"

            # Nettoyage
            s_clean = sujet_val.lower().replace(" ", "")
            a_clean = action_val.lower().replace(" ", "")
            c_clean = categorie_val.lower().replace(" ", "")

            nom_fichier = (
                f"interaction_{s_clean}_{a_clean}_{c_clean}_{timestamp_clean}.json"
            )

            chemin_historique = self.auditor.get_path("historique")
            if not chemin_historique:
                self.logger.log_error("Chemin 'historique' introuvable")
                return False

            chemin_fichier = Path(chemin_historique) / nom_fichier

            # 🛡️👁️‍🗨️🛡️   # VALIDATION FORMAT SORTIE
            self.auditor.valider_format_sortie(interaction_element)

            # --- 2. Écriture du Fichier JSON (La source pour le résumé différé) ---
            try:
                with open(chemin_fichier, "w", encoding="utf-8") as f:
                    json.dump(
                        asdict(interaction_element),
                        f,
                        ensure_ascii=False,
                        indent=2,
                        cls=CustomJSONEncoder,
                    )
                    f.write("\n")
            except Exception as e:
                self.logger.log_error(f"Erreur écriture fichier historique: {e}")
                return False

            self.logger.log_thought(f"📜 Interaction mémorisée (Tampon): {nom_fichier}")

            # --- 3. Vectorisation IMMÉDIATE (Pour le court terme) ---
            # NOTE : On garde la vectorisation immédiate de l'échange brut pour que la mémoire
            # court terme fonctionne tout de suite. Le résumé différé viendra consolider plus tard.
            if self.moteur_vectoriel:
                try:
                    texte_concat = (
                        f"{interaction_element.prompt}\n{interaction_element.reponse}"
                    )
                    meta = {
                        "fichier": str(chemin_fichier),
                        "timestamp": interaction_element.meta.timestamp,
                        "session_id": interaction_element.meta.session_id,
                        "type": "historique_brut",  # Différent du "golden_path" futur
                    }
                    self.moteur_vectoriel.ajouter_fragment(texte_concat, meta)
                except Exception as e:
                    self.logger.log_warning(f"Echec vectorisation immédiate: {e}")

            # --- 4. Indexation Whoosh ---
            if hasattr(self, "agent_recherche"):
                try:
                    self.agent_recherche.update_index(
                        contenu=f"{interaction_element.prompt} {interaction_element.reponse}",
                        type_memoire="historique",
                        sujet=sujet_val,
                        action=action_val,
                        categorie=categorie_val,
                        nouveau_fichier=str(chemin_fichier),
                    )
                except Exception as e:
                    self.logger.log_warning(f"Echec Whoosh: {e}")

            return True

        except Exception as e:
            self.logger.log_error(
                f"Erreur fatale memoriser_interaction: {e}", exc_info=True
            )
            return False

    def journaliser_trace_reflexive(
        self, trace_markdown: str, type_erreur: str, classification: str
    ):
        """
        Ancre les processus de métacognition (Réflexion sur soi) dans la mémoire.

        Sauvegarde les rapports générés par l'AgentReflexor (Diagnostiques d'erreurs,
        auto-critiques) et les vectorise. Cela permet au système, dans le futur,
        de se "souvenir qu'il s'est déjà trompé" sur un sujet similaire (Learning form Failure).

        Args:
            trace_markdown (str): Le rapport d'analyse au format lisible.
            type_erreur (str): La catégorie de l'erreur (ex: "Hallucination", "Code").
        """
        # 1. Demander le *dossier* 'reflexive'
        chemin_dossier_reflexif = self.auditor.get_path("reflexive")

        if not chemin_dossier_reflexif:
            self.logger.log_error("❌ Dossier 'reflexive' introuvable dans l'Auditor.")
            return

        chemin_fichier = Path(chemin_dossier_reflexif) / "journal_de_doute_reflexif.md"

        try:
            # 3. Écrire dans le fichier .md (en mode 'append')
            with open(chemin_fichier, "a", encoding="utf-8") as f:
                f.write(trace_markdown + "\n")

            self.logger.info(
                f"✅ Trace réflexive ({type_erreur}) ajoutée au journal .md."
            )

            # 4. AJOUTER AU MOTEUR VECTORIEL (SÉMANTIQUE)
            # Vectorisation
            if self.moteur_vectoriel:
                meta = {
                    "type": "reflexive",
                    "origine": "boucle_reflexive",
                    "fichier": str(chemin_fichier),
                    "type_erreur": type_erreur,
                    "classification": classification,
                }
                self.moteur_vectoriel.ajouter_fragment(trace_markdown, meta)
                self.moteur_vectoriel._sauvegarder_index()
                self.logger.info("✅ Trace réflexive vectorisée.")

            # Whoosh
            if hasattr(self, "agent_recherche"):
                self.agent_recherche.update_index(
                    contenu=trace_markdown,
                    type_memoire="reflexive",
                    sujet=classification,
                    action="reflexion",
                    categorie="gouvernance",
                )
            self.logger.info("✅ Index Whoosh (reflexive) mis à jour.")

        except Exception as e:
            self.logger.log_error(
                f"Erreur lors de la journalisation/indexation de la trace réflexive: {e}"
            )

    # ================================================================
    # MÉTHODES DE SAUVEGARDE DU CODE
    # ================================================================
    def sauvegarder_artefacts_code(self, artefacts: List[Dict]) -> bool:
        """
        Extrait, filtre et archive le capital code généré par le LLM.

        Rôle double :
        1. **Extraction Physique** : Sauvegarde les snippets dans des fichiers réels (.py, .js)
           pour usage ultérieur ou audit.
        2. **Base de Connaissance Code (RAG)** : Alimente une base JSONL spécifique (`code_chunks.jsonl`)
           qui servira de contexte technique pour les futures tâches de développement.

        Filtre Intelligent :
           Détecte et ignore automatiquement les "Tool Calls" (JSON de commande) pour ne pas
           polluer la base de code avec des instructions système.

        Args:
            artefacts (List[Dict]): Liste des blocs de code extraits de la réponse.
        """
        if not artefacts:
            return True

        # 1. Chargement mapping extensions depuis YAML
        cfg_art = self.config.get("artefacts_code", {})
        ext_map = cfg_art.get(
            "extensions_map",
            {
                "python": "py",
                "javascript": "js",
                "json": "json",
                "html": "html",
                "css": "css",
            },
        )
        ignore_tools = cfg_art.get("ignorer_tool_calls", True)

        try:
            # Chemins
            root_memoire = Path(self.auditor.get_path("memoire"))
            dir_extraits = root_memoire / "code" / "code_extraits"
            file_db_rag = root_memoire / "code" / "code_chunks.jsonl"

            dir_extraits.mkdir(parents=True, exist_ok=True)
            # Assurer que le dossier parent du fichier JSONL existe
            file_db_rag.parent.mkdir(parents=True, exist_ok=True)

            count_ok = 0

            for art in artefacts:
                # --- FILTRE : BYPASS TOOL CALLS ---
                # Si c'est du JSON et que ça contient la signature d'un outil ("function": "...")
                # On ne sauvegarde PAS, car c'est une commande système, pas du code projet.
                if ignore_tools and art.get("langage", "").lower() == "json":
                    contenu_lower = art.get("contenu", "").lower()

                    # DÉTECTION GÉNÉRIQUE : On cherche la clé "function" suivie d'un nom
                    # On couvre les variantes d'espacement json : "function": ou "function" :
                    is_tool_call = ('"function":' in contenu_lower) or (
                        '"function" :' in contenu_lower
                    )

                    # On vérifie aussi la présence d'"arguments" pour être sûr
                    has_arguments = ('"arguments":' in contenu_lower) or (
                        '"arguments" :' in contenu_lower
                    )

                    if is_tool_call and has_arguments:
                        self.logger.info(
                            f"🚫 Artefact ignoré (Tool Call détecté : {art.get('id')})"
                        )
                        continue
                # ----------------------------------
                # 3. Utilisation de la map YAML
                lang = art.get("langage", "text").lower()
                ext = ext_map.get(lang, "txt")  # Utilise la map chargée dynamiquement

                ts_simple = datetime.now().strftime("%Y%m%d")
                filename = f"artifact_{ts_simple}_{art['id']}.{ext}"
                filepath = dir_extraits / filename

                if not filepath.exists():
                    try:
                        with open(filepath, "w", encoding="utf-8") as f:
                            f.write(art["contenu"])
                    except Exception:
                        pass

                # 2. Préparation Entrée RAG (Compatibilité ContexteCode)
                raw_analyse = art.get("analyse", art.get("metadata_analyse", {}))

                if is_dataclass(raw_analyse):
                    analyse_obj = raw_analyse
                else:
                    analyse_obj = AnalyseContenu(
                        mode=raw_analyse.get("mode", "AST"),
                        fonctions=raw_analyse.get("fonctions", []),
                        classes=raw_analyse.get("classes", []),
                        imports=raw_analyse.get("imports", []),
                        docstring=raw_analyse.get("docstring"),
                        erreurs=raw_analyse.get("erreurs"),
                        extras=raw_analyse.get("extras", {}),
                    )

                artefact_obj = ArtefactCode(
                    id=art.get("id", "unknown"),
                    hash=art.get("hash", "nohash"),
                    langage=art.get("langage", "python"),
                    contenu=art.get("contenu", ""),
                    timestamp=art.get("timestamp", datetime.now().isoformat()),
                    analyse=analyse_obj,
                    type="snippet_llm",
                )
                # 🛡️👁️‍🗨️🛡️       # VALIDATION FORMAT SORTIE
                self.auditor.valider_format_sortie(artefact_obj)

                # 3. Append to JSONL
                with open(file_db_rag, "a", encoding="utf-8") as fdb:
                    json.dump(asdict(artefact_obj), fdb, ensure_ascii=False)
                    fdb.write("\n")

                count_ok += 1

            self.logger.log_thought(
                f"💾 Code archivé : {count_ok} artefacts sauvegardés (ArtefactCode)."
            )
            return True

        except Exception as e:
            self.logger.log_error(
                f"❌ Erreur sauvegarde artefacts code : {e}", exc_info=True
            )
            return False

    # ================================================================
    # 3. SAUVEGARDE GÉNÉRIQUE (Pour Reflexor etc.)
    # ================================================================
    def sauvegarder_memoire(
        self, contenu: Any, type_memoire: str, nom_fichier: str
    ) -> bool:
        """
        Interface d'écriture générique pour les modules externes ou les injecteurs manuels.

        Permet de persister des données arbitraires (Feedback utilisateur, Configuration,
        Données brutes) dans l'arborescence mémoire gérée, en déléguant la résolution
        des chemins sécurisés à l'Auditor.

        Args:
            contenu (Any): Donnée à écrire (Dict -> JSON, Str -> Texte).
            type_memoire (str): Clé de dossier cible (ex: "reflexive", "persistante").
        """
        try:
            # 1. Résolution du chemin de base via l'Auditor
            # type_memoire peut être "reflexive", "persistante", "brute", etc.
            chemin_base = self.auditor.get_path(type_memoire)

            if not chemin_base:
                self.logger.log_error(
                    f"Type de mémoire inconnu ou chemin introuvable : {type_memoire}"
                )
                return False

            # 2. Construction du chemin complet
            # On gère le cas où nom_fichier contient déjà un sous-dossier (ex: feedback/...)
            full_path = Path(chemin_base) / nom_fichier

            # Assurer que le dossier parent existe
            full_path.parent.mkdir(parents=True, exist_ok=True)

            # 3. Écriture (JSON ou Texte)
            with open(full_path, "w", encoding="utf-8") as f:
                if isinstance(contenu, (dict, list)):
                    # Import local pour éviter les dépendances circulaires
                    from agentique.base.contrats_interface import CustomJSONEncoder

                    json.dump(
                        contenu, f, cls=CustomJSONEncoder, ensure_ascii=False, indent=2
                    )
                else:
                    f.write(str(contenu))

            self.logger.info(
                f"💾 Mémoire sauvegardée ({type_memoire}) : {full_path.name}"
            )
            return True

        except Exception as e:
            self.logger.log_error(
                f"❌ Erreur sauvegarde mémoire générique : {e}", exc_info=True
            )
            return False

    # ================================================================
    # ✅ NOUVELLE MÉTHODE : VECTORISATION DÉDIÉE AUX RÈGLES
    # ================================================================
    def vectoriser_regle(self, contenu_regle: str, metadata: Dict) -> bool:
        """
        Injecte une nouvelle loi dans le "Moteur Législatif" (Index Vectoriel Dédié).

        Implémente une séparation architecturale critique : les règles de gouvernance
        ne sont pas mélangées aux souvenirs narratifs. Cela garantit que lors d'une
        recherche de "Lois", le système ne récupère pas de "Discussions sur les lois",
        mais bien les directives elles-mêmes.

        Args:
            contenu_regle (str): Le texte impératif de la règle.
            metadata (Dict): Contexte de création (ex: Trigger, Date, Origine).
        """
        if not self.moteur_regles:
            self.logger.log_error(
                "❌ Moteur Législatif non disponible. Impossible de vectoriser la règle."
            )
            return False

        try:
            # On force le type pour être sûr
            metadata["type"] = "regle_gouvernance"
            metadata["sub_type"] = "vector_store_dedie"

            self.moteur_regles.ajouter_fragment(texte=contenu_regle, meta=metadata)
            self.logger.info(
                f"⚖️ Règle vectorisée dans le moteur législatif (ID: {metadata.get('trigger', 'N/A')})"
            )
            return True
        except Exception as e:
            self.logger.log_error(f"Erreur vectorisation règle : {e}")
            return False

    # ================================================================
    # MÉTHODES UTILITAIRES
    # ================================================================

    def obtenir_statistiques(self) -> Dict[str, Any]:
        """Retourne les statistiques de l'agent via le StatsManager."""
        # Note : Ne pas confondre avec obtenir_etat_memoire qui est plus détaillé.
        return self.stats_manager.obtenir_statistiques()
