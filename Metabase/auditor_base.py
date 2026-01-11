#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AUDITOR BASE - Gardien de la Conformité et des Standards
=========================================================
Version: 1.2 - Chemins corrigés avec dossier base
"""

import json
import yaml
from pathlib import Path
import os
from datetime import datetime
from dataclasses import dataclass, fields, is_dataclass
from typing import (
    Dict,
    Any,
    Optional,
    List,
    Tuple,
    get_type_hints,
    get_origin,
    get_args,
)
from pathlib import Path

# Imports depuis le dossier base - CHEMINS CORRECTS
from agentique.base.config_paths import ROOT_DIR


@dataclass
class StandardsAgents:
    """
    Standards RÉELS extraits des agents existants
    Mise à jour : Ajout des formats de sortie autorisés (Dataclasses).
    """

    # Semi - Agent principal
    semi = {
        "paths": {
            "agent_dir": "agentique/Semi",
            "logs": "agentique/Semi/logs",
        },
        "config": "agentique/Semi/config_semi.yaml",
        "formats_sortie": ["Interaction"],
        "stats_specifiques": [],
    }

    # AgentMemoire
    memoire = {
        "paths": {
            "agent_dir": "agentique/sous_agents_gouvernes/agent_Memoire",
            "logs": "agentique/sous_agents_gouvernes/agent_Memoire/logs",
            "config": "agentique/sous_agents_gouvernes/agent_Memoire/config_memoire.yaml",
            "memoire": "memoire",
            "base": "memoire",
            "brute": "memoire/brute",
            "historique": "memoire/historique",
            "persistante": "memoire/persistante",
            "reflexive": "memoire/reflexive",
            "regles": "memoire/reflexive/regles",
            "feedback": "memoire/reflexive/feedback",
            "vectorielle": "memoire/vectorielle",
            "vectorielle_regles": "memoire/vectorielle_regles",
            "connaissances": "memoire/connaissances",
            "modules_formation": "memoire/modules_formation",
        },
        "formats_sortie": ["Interaction", "ArtefactCode"],
        "stats_specifiques": [
            "recuperations",
            "sauvegardes",
            "erreurs",
            "items_travail_ajoutes",
        ],
    }

    moteurvectoriel = {
        "paths": {
            "agent_dir": "agentique/sous_agents_gouvernes/agent_Memoire",
            "memoire": "memoire",
            "vectorielle": "memoire/vectorielle",
            "vectorielle_regles": "memoire/vectorielle_regles",
            "logs": "agentique/sous_agents_gouvernes/agent_Memoire/logs",
        },
        "config": {},
        "stats_specifiques": ["fragments_ajoutes", "recherches_effectuees"],
    }

    processeurbrutepersistante = {
        "paths": {
            "agent_dir": "agentique/sous_agents_gouvernes/agent_Memoire",
            "historique": "memoire/historique",
            "persistante": "memoire/persistante",
            "logs": "agentique/sous_agents_gouvernes/agent_Memoire/logs_processeur",
        },
        "config": {},
        "formats_sortie": ["Interaction"],
        "stats_specifiques": [
            "items_traites",
            "items_valides",
            "items_invalides",
            "fichiers_crees",
            "erreurs",
        ],
    }

    # AgentAuditor
    auditor = {
        "paths": {
            "agent_dir": "agentique/sous_agents_gouvernes/agent_Auditor",
            "logs": "agentique/sous_agents_gouvernes/agent_Auditor/logs",
            "config": "agentique/sous_agents_gouvernes/agent_Auditor/config_auditor.yaml",
        },
        "stats_specifiques": [],
    }

    # AgentJuge
    juge = {
        "paths": {
            "agent_dir": "agentique/sous_agents_gouvernes/agent_Juge",
            "logs": "agentique/sous_agents_gouvernes/agent_Juge/logs",
            "config": "agentique/sous_agents_gouvernes/agent_Juge/config_juge.yaml",
        },
        "formats_sortie": ["ResultatJuge"],
        "stats_specifiques": [],
    }

    entraineur = {
        "paths": {
            "agent_dir": "agentique/sous_agents_gouvernes/agent_Entraineur",
            "logs": "agentique/sous_agents_gouvernes/agent_Entraineur/logs",
            "config": "agentique/sous_agents_gouvernes/agent_Entraineur/config_entraineur.yaml",
        },
        "stats_specifiques": [],
    }

    autodatasetbuilder = {
        "paths": {
            "agent_dir": "agentique/sous_agents_gouvernes/agent_Entraineur/autodataset_builder",
            "logs": "agentique/sous_agents_gouvernes/agent_Entraineur/logs",
            "config": [],
        },
        "stats_specifiques": [],
    }

    moteurllm = {
        "paths": {
            "agent_dir": "agentique/sous_agents_gouvernes/agent_Parole/moteurs",
            "logs": "agentique/sous_agents_gouvernes/agent_Parole/moteurs/logs",
            "config": "agentique/sous_agents_gouvernes/agent_Parole/moteurs/config_moteurllm.yaml",
        },
        "stats_specifiques": [],
    }

    moteurminillm = {
        "paths": {
            "agent_dir": "agentique/sous_agents_gouvernes/agent_Parole/moteurs",
            "logs": "agentique/sous_agents_gouvernes/agent_Parole/moteurs/logs",
            "config": "agentique/sous_agents_gouvernes/agent_Parole/moteurs/config_moteur_mini_llm.yaml",
        },
        "stats_specifiques": [],
    }
    minillm = moteurminillm

    reflexor = {
        "paths": {
            "agent_dir": "agentique/sous_agents_gouvernes/agent_Reflexor",
            "logs": "agentique/sous_agents_gouvernes/agent_Reflexor/logs",
            "config": "agentique/sous_agents_gouvernes/agent_Reflexor/config_reflexor.yaml",
        },
        "formats_sortie": ["dict", "EntreeJournalReflexif"],
        "stats_specifiques": ["analyses_effectuees", "corrections_approuvees"],
    }

    cognitivelogger = {
        "paths": {"logs": "agentique/Semi/logs"},
        "config": {},
        "stats_specifiques": [],
    }

    contexte = {
        "paths": {
            "agent_dir": "agentique/sous_agents_gouvernes/agent_Contexte",
            "logs": "agentique/sous_agents_gouvernes/agent_Contexte/logs",
            "config": "agentique/sous_agents_gouvernes/agent_Contexte/config_contexte.yaml",
        },
        "formats_sortie": ["ResultatContexte"],
        "stats_specifiques": [],
    }

    parole = {
        "paths": {
            "agent_dir": "agentique/sous_agents_gouvernes/agent_Parole",
            "logs": "agentique/sous_agents_gouvernes/agent_Parole/logs",
            "config": "agentique/sous_agents_gouvernes/agent_Parole/config_parole.yaml",
            "memoire": "memoire",
        },
        "formats_sortie": ["str"],
        "stats_specifiques": [],
    }

    recherche = {
        "paths": {
            "agent_dir": "agentique/sous_agents_gouvernes/agent_Recherche",
            "logs": "agentique/sous_agents_gouvernes/agent_Recherche/logs",
            "memoire": "memoire",
            "reflexive": "memoire/reflexive",
            "brute": "memoire/brute",
            "historique": "memoire/historique",
            "persistante": "memoire/persistante",
            "feedback": "memoire/reflexive/feedback",
            "regles": "memoire/reflexive/regles",
            "connaissances": "memoire/connaissances",
            "modules_formation": "memoire/modules_formation",
            "vectorielle": "memoire/vectorielle",
            "woosh_index": "memoire/whoosh_index",
            "config": "agentique/sous_agents_gouvernes/agent_Recherche/config_recherche.yaml",
        },
        "formats_sortie": [
            "ResultatRecherche",
            "ResultatRechercheWeb",
            "Regle",
            "FichierReadme",
            "DocumentationTechnique",
            "Souvenir",
        ],
        "stats_specifiques": [
            "recherches_effectuees",
            "recherches_hybrides",
            "recherches_semantiques",
            "fichiers_indexes",
        ],
    }

    code = {
        "paths": {
            "agent_dir": "agentique/sous_agents_gouvernes/agent_Code",
            "logs": "agentique/sous_agents_gouvernes/agent_Code/logs",
            "memoire": "memoire",
            "config": "agentique/sous_agents_gouvernes/agent_Code/config_code.yaml",
        },
        "formats_sortie": ["ResultatCode", "ContexteCode", "Souvenir"],
        "stats_specifiques": [
            "requetes_code",
            "chunks_recuperes",
            "fichiers_concernes",
        ],
    }

    codeextractormanager = {
        "paths": {
            "agent_dir": "agentique/sous_agents_gouvernes/agent_Code",
            "logs": "agentique/sous_agents_gouvernes/agent_Code/logs",
            "config": "agentique/sous_agents_gouvernes/agent_Code/config_recherchecode.yaml",
            "memoire": "memoire",
        },
        "stats_specifiques": ["snippets_analyses", "artefacts_generes"],
    }

    moteurvecteurcode = {
        "paths": {
            "logs": "agentique/sous_agents_gouvernes/agent_Code/logs",
            "root": ".",
            "memoire": "memoire",
            "config": "agentique/sous_agents_gouvernes/agent_Code/config_code.yaml",
        },
        "stats_specifiques": ["fichiers_scannes", "chunks_generes", "temps_scan"],
    }

    intentiondetector = {
        "paths": {
            "agent_dir": "agentique/Semi/classes_cognitives/Intention_Detector",
            # ✅ NOTE : Si ce dossier n'existe pas, l'auditor le signalera. C'est normal tant que le modèle n'est pas entraîné.
            "classifier_dir": "data_training_center/Semi/intention_detector_SBERT/intention_classifier_v1.pth",
            "logs": "agentique/Semi/classes_cognitives/logs",
            "config": "agentique/sous_agents_gouvernes/agent_Parole/moteurs/config_moteur_mini_llm.yaml",
        },
        "formats_sortie": ["ResultatIntention"],
        "stats_specifiques": [],
    }

    rechercheweb = {
        "paths": {
            "agent_dir": "agentique/sous_agents_gouvernes/agent_Recherche",
            "logs": "agentique/sous_agents_gouvernes/agent_Recherche/logs",
        },
        "config": [],
        "stats_specifiques": [],
    }


class AuditorBase:
    """
    Classe d'audit - NE CRÉE AUCUN DOSSIER
    Vérifie seulement l'existence
    """

    def __init__(self, nom_agent: str = "AuditorBase"):
        self.nom_agent = nom_agent.lower()
        self.standards = StandardsAgents()
        self._config_agent = None
        self._valeurs_par_defaut = {
            "paths": {},
            "formats_entree": ["dict"],
            "formats_sortie": ["dict"],
            "config": {},
            "stats_specifiques": [],
        }
        # 1. On récupère la config brute de l'agent depuis StandardsAgents
        # Cela permet d'avoir les chemins définis dans le code (Source de Vérité)
        data_agent = getattr(self.standards, self.nom_agent, self._valeurs_par_defaut)

        # 2. On isole les chemins pour la vérification
        self.paths = data_agent.get("paths", {})

        # 3. On définit le chemin des logs runtime
        self.runtime_log_path = (
            ROOT_DIR
            / "agentique"
            / "sous_agents_gouvernes"
            / "agent_Auditor"
            / "logs"
            / "runtime_violations.jsonl"
        )

        # 4. Vérification physique
        self.verifier_integrite_systeme()

    def get_config(self) -> Dict[str, Any]:
        """Retourne la config pour cet agent"""
        if self._config_agent is None:
            self._config_agent = getattr(
                self.standards, self.nom_agent, self._valeurs_par_defaut
            )
        return self._config_agent

    def recuperer_racine_projet(self) -> Path:
        """
        ACCESSEUR OFFICIEL : Retourne la racine absolue du projet (ROOT_DIR).
        Permet aux agents de valider la sécurité des chemins sans importer config_paths.
        """
        return ROOT_DIR

    def get_path(
        self, path_type: str, nom_agent: Optional[str] = None
    ) -> Optional[str]:
        """
        Récupère un chemin configuré en utilisant la structure StandardsAgents.
        """
        # 1. Détermine le nom de l'agent à cibler (en minuscules pour correspondre aux standards)
        nom_agent = nom_agent.lower() if nom_agent else self.nom_agent

        # 2. Récupère la configuration de cet agent depuis la classe StandardsAgents
        #    On utilise getattr pour chercher dynamiquement (ex: self.standards.semi, self.standards.moteurllm)
        config_agent = getattr(self.standards, nom_agent, None)

        if not config_agent:
            # On ne peut pas utiliser self.logger ici car l'auditor est créé avant le logger.
            # Un simple print est plus sûr dans ce contexte.
            print(
                f"ERREUR AUDITOR: Agent '{nom_agent}' non trouvé dans StandardsAgents."
            )
            return None

        # 3. Cherche la clé de chemin demandée dans la configuration de l'agent
        #    D'abord directement, puis dans le sous-dictionnaire "paths"
        path_value = config_agent.get(path_type) or config_agent.get("paths", {}).get(
            path_type
        )

        if path_value:
            # 4. Construit le chemin absolu en utilisant ROOT_DIR importé en haut du fichier
            return str(ROOT_DIR / path_value)

        print(
            f"AVERTISSEMENT AUDITOR: Type de chemin '{path_type}' non trouvé pour l'agent '{nom_agent}'."
        )
        return None

    def chemin_existe(self, type_path: str) -> bool:
        """Vérifie si un chemin existe SANS le créer"""
        chemin = self.get_path(type_path)
        if not chemin:
            return False
        return Path(chemin).exists()

    def get_param(self, nom_param: str, defaut: Any = None) -> Any:
        """Récupère un paramètre de configuration"""
        config = self.get_config()
        params = config.get("config", {})
        return params.get(nom_param, defaut)

    def get_formats_entree(self) -> List[str]:
        """Retourne les formats d'entrée acceptés"""
        return self.get_config().get("formats_entree", ["dict"])

    def get_formats_sortie(self) -> List[str]:
        """Retourne les formats de sortie produits"""
        return self.get_config().get("formats_sortie", ["dict"])

    def get_stats_specifiques(self) -> List[str]:
        """Retourne la liste des stats spécifiques à tracker"""
        return self.get_config().get("stats_specifiques", [])

    def valider_format_entree(self, data: Any) -> bool:
        """Valide le format d'entrée"""
        formats_acceptes = self.get_formats_entree()

        # Type de base
        type_data = type(data).__name__
        if type_data in formats_acceptes:
            return True

        # Dataclasses
        if hasattr(data, "__dataclass_fields__"):
            return data.__class__.__name__ in formats_acceptes

        return False

    def _persister_violation(self, type_violation: str, message: str, contexte: str):
        """
        Écrit la violation dans un fichier JSONL partagé.
        L'AgentAuditor pourra relire ce fichier pour son rapport global.
        """
        try:
            entry = {
                "timestamp": datetime.now().isoformat(),
                "agent_source": self.nom_agent,
                "type": type_violation,
                "message": message,
                "contexte": contexte,
            }

            # On s'assure que le dossier existe (au cas où l'AgentAuditor n'a pas encore tourné)
            if not self.runtime_log_path.parent.exists():
                return  # On évite de créer des dossiers depuis la base si possible, ou on log silencieusement

            # Mode 'append' pour ajouter la ligne sans écraser l'historique
            with open(self.runtime_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        except Exception as e:
            print(f"⚠️ AUDITOR BASE: Impossible de persister la violation: {e}")

    def valider_format_sortie(self, data: Any) -> bool:
        """
        Validation stricte du format de sortie.
        Enclenche maintenant une vérification PROFONDE (Deep Type Checking).
        """
        valid = self._validation_generique(data, self.get_formats_sortie())

        if not valid:
            msg = f"L'objet {type(data).__name__} n'est pas autorisé. Attendus: {self.get_formats_sortie()}"
            print(f"🚨 AUDITOR ALERTE SORTIE [{self.nom_agent}]: {msg}")
            self._persister_violation("FORMAT_SORTIE_INVALID", msg, "Sortie Agent")

        if valid and is_dataclass(data):
            if not self._valider_champs_profond(data):
                pass  # L'erreur est loggée dans la méthode profonde

        return valid

    def valider_echange(self, data: Any, agent_destination: str) -> bool:
        """
        Valide un échange de données vers un autre agent

        Args:
            data: Données à envoyer
            agent_destination: Nom de l'agent destinataire

        Returns:
            True si l'échange est valide
        """
        # Vérifier format de sortie
        if not self.valider_format_sortie(data):
            return False

        # Créer auditor temporaire pour destination
        auditor_dest = AuditorBase(agent_destination)
        return auditor_dest.valider_format_entree(data)

    def _validation_generique(self, data: Any, formats_attendus: List[str]) -> bool:
        """Logique de base pour vérifier le conteneur."""
        # Tuples
        if isinstance(data, tuple) and "tuple" in formats_attendus:
            return True

        # Types de base (str, dict, list)
        type_data = type(data).__name__
        if type_data in formats_attendus:
            return True

        # Dataclasses
        if hasattr(data, "__dataclass_fields__"):
            return data.__class__.__name__ in formats_attendus

        return False

    def _valider_champs_profond(self, dataclass_instance: Any) -> bool:
        """
        Vérifie récursivement que le contenu des champs correspond aux types déclarés.
        """
        try:
            type_hints = get_type_hints(dataclass_instance.__class__)

            for field in fields(dataclass_instance):
                nom_champ = field.name
                valeur = getattr(dataclass_instance, nom_champ)
                type_attendu = type_hints.get(nom_champ)

                if valeur is None:
                    continue

                # Gestion des LISTES (Generic types comme List[Regle])
                origin = get_origin(type_attendu)
                if origin is list or origin is List:
                    args = get_args(type_attendu)
                    if not args:
                        continue

                    type_item_attendu = args[0]

                    if isinstance(valeur, list) and len(valeur) > 0:
                        premier_item = valeur[0]
                        if is_dataclass(premier_item):
                            nom_classe_item = premier_item.__class__.__name__
                            nom_classe_attendue = type_item_attendu.__name__

                            if nom_classe_item != nom_classe_attendue:
                                msg = f"Champ '{nom_champ}' contient {nom_classe_item} au lieu de {nom_classe_attendue}"
                                print(f"🚨 ALERTE TYPE PROFONDE : {msg}")

                                # ✅ PERSISTANCE
                                self._persister_violation(
                                    "VIOLATION_CONTRAT_PROFOND",
                                    msg,
                                    f"Dataclass {dataclass_instance.__class__.__name__}",
                                )
                                return False

            return True

        except Exception as e:
            print(f"⚠️ Erreur lors de la validation profonde : {e}")
            return True  # On ne bloque pas en cas d'erreur technique d'audit

    def valider_utilisation_complete(self, objet_a_valider: Any) -> bool:
        """Vérifie qu'une dataclass est complète (champs non vides)."""
        class_name = "Inconnu"
        unused = set()

        # CAS 1 : Wrapper (TrackedDataclass)
        if hasattr(objet_a_valider, "get_unused_fields"):
            try:
                unused = objet_a_valider.get_unused_fields()
                # Récupération sécurisée du nom de la classe
                if hasattr(objet_a_valider, "get_class_name"):
                    class_name = objet_a_valider.get_class_name()
                else:
                    class_name = objet_a_valider.__class__.__name__
            except Exception:
                pass

        # CAS 2 : Dataclass Pure (Inspection directe)
        elif is_dataclass(objet_a_valider):
            class_name = objet_a_valider.__class__.__name__
            try:
                for champ in fields(objet_a_valider):
                    valeur = getattr(objet_a_valider, champ.name)
                    # Définition d'un champ "vide" : None ou collection vide
                    if valeur is None or (
                        isinstance(valeur, (list, dict, str)) and len(valeur) == 0
                    ):
                        unused.add(champ.name)
            except Exception:
                pass

        else:
            # Ni l'un ni l'autre, on ignore
            return True

        # REPORTING
        if unused:
            unused_list = sorted(list(unused))
            msg = f"Dataclass '{class_name}' a des champs vides/ignorés : {unused_list}"

            # 1. Alerte Console immédiate
            print(f"⚠️ AUDITOR WARNING: {msg}")

            # 2. Persistance pour le rapport final (CRITIQUE)
            self._persister_violation("CHAMPS_IGNORES", msg, class_name)

            # On retourne True pour ne pas bloquer l'exécution (Mode Warning)
            return True

        return True

    def verifier_integrite_systeme(self):
        """
        Vérifie l'existence physique des dossiers définis dans self.paths.
        Utilise ROOT_DIR pour garantir des chemins absolus.
        """
        if not self.paths:
            return

        missing = []

        # On itère sur le dictionnaire self.paths extrait de StandardsAgents
        for key, val in self.paths.items():
            # On ignore les clés qui ne sont pas des chemins (ex: settings)
            if not isinstance(val, (str, Path)):
                continue

            # Construction du chemin absolu
            full_path = ROOT_DIR / val

            if not full_path.exists():
                missing.append(f"{key} -> {full_path}")

        if missing:
            print(f"❌ [AuditorBase:{self.nom_agent}] Chemins manquants : {missing}")

    # =========================================================
    # ✅ MÉTHODES AJOUTÉES POUR CONFORMITÉ META_AGENT & SÉCURITÉ
    # =========================================================

    def enregistrer_stat(self, nom_methode: str, donnees: Dict[str, Any]) -> None:
        """
        Enregistre une statistique d'exécution provenant de MetaAgent.
        Sert de pont vers le système de logs ou de dashboarding.
        Accepte silencieusement les données pour ne pas briser le flux.
        """
        # TODO: Connecter à un writer asynchrone pour stats_execution.json
        # Pour l'instant, on laisse passer pour éviter le crash dans META_agent
        pass

    def signal_gouvernance(self, message: str, niveau: str = "ALERTE") -> None:
        """
        Permet à un agent de signaler un problème de gouvernance ou de sécurité.
        """
        prefixe = "🚨" if niveau == "CRITIQUE" else "⚠️"
        print(f"{prefixe} GOUVERNANCE [{self.nom_agent.upper()}] : {message}")


# =============================================================================
# TRACKING DE DATACLASS (Pour validation runtime)
# =============================================================================


class TrackedDataclass:
    """
    Wrapper qui trace quels champs d'une dataclass sont accédés.
    Permet de détecter les champs ignorés lors de la construction de prompts.
    """

    def __init__(self, dataclass_instance):
        object.__setattr__(self, "_instance", dataclass_instance)
        object.__setattr__(self, "_accessed_fields", set())
        object.__setattr__(self, "_class_name", dataclass_instance.__class__.__name__)

    def __getattribute__(self, name):
        # Ne pas tracker les attributs privés
        if name.startswith("_"):
            return object.__getattribute__(self, name)

        # Enregistrer l'accès
        accessed = object.__getattribute__(self, "_accessed_fields")
        accessed.add(name)

        # Retourner la valeur du champ
        instance = object.__getattribute__(self, "_instance")
        return getattr(instance, name)

    def get_unused_fields(self):
        """Retourne les champs de la dataclass qui n'ont jamais été accédés"""
        instance = object.__getattribute__(self, "_instance")
        all_fields = set(instance.__dataclass_fields__.keys())
        accessed = object.__getattribute__(self, "_accessed_fields")
        return all_fields - accessed

    def get_accessed_fields(self):
        """Retourne les champs qui ont été accédés"""
        return object.__getattribute__(self, "_accessed_fields")

    def get_class_name(self):
        """Retourne le nom de la dataclass wrappée"""
        return object.__getattribute__(self, "_class_name")


class AuditorGlobal:
    """Singleton pour accès global aux standards"""

    _instance = None
    _standards = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._standards = StandardsAgents()
        return cls._instance
