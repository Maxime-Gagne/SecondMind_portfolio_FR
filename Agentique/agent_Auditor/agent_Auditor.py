#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AgentAuditor - Gardien de l'Intégrité, de la Sécurité et de la Conformité
Module responsable de l'audit statique (Code) et dynamique (Runtime) du système.

Ce module agit comme une autorité de régulation interne ("Internal Affairs") :
1.  **Analyse Statique (AST)** : Scanne le code source pour détecter :
    - Les violations de contrats (Arguments manquants dans les Dataclasses).
    - Les problèmes d'hygiène (Variables mortes).
    - Les failles de sécurité (Commandes destructives dans les sanctuaires).
    - L'utilisation de "Shadow Objects" (Dictionnaires imitant des objets).
2.  **Surveillance Dynamique** :
    - Trace l'utilisation des objets au runtime (Champs ignorés par l'AgentParole).
    - Vérifie la cohérence des flux de données (Production LLM vs Persistance Disque).
3.  **Maintenance** :
    - Cartographie automatique du projet (Project Map).
    - Normalisation de l'encodage des fichiers (UTF-8 strict).

Rôle Architectural :
    Garantit que le système ne dérive pas vers le chaos entropique. Il valide que
    la réalité du code correspond aux spécifications de l'architecture.
"""

import json
import re
import ast
import yaml
import inspect
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Set, Optional

from agentique.base.META_agent import AgentBase
from agentique.base.config_paths import ROOT_DIR

# On importe le contrat pour extraire le vocabulaire officiel
import agentique.base.contrats_interface as contrats

# =============================================================================
# TRACKING DE DATACLASS (Pour validation runtime)
# =============================================================================
ENCODING_REGISTRY_PATH = Path(
    "D:/rag_personnel/agentique/sous_agents_gouvernes/agent_Auditor/auditor_encoding_registry.json"
)


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


# =============================================================================
# VISITEURS AST (Les Enquêteurs)
# =============================================================================


class ContractComplianceVisitor(ast.NodeVisitor):
    """
    Vérifie que les instanciations de Dataclasses respectent la définition officielle.
    Vérifie les champs INVALIDES (intrus) et les champs MANQUANTS (obligatoires).
    """

    def __init__(self, definitions_contrats: Dict[str, Dict[str, Set[str]]]):
        # definitions structure: {'NomClasse': {'all': {a,b,c}, 'required': {a,b}}}
        self.definitions = definitions_contrats
        self.violations = []

    def visit_Call(self, node):
        nom_classe = None
        if isinstance(node.func, ast.Name):
            nom_classe = node.func.id

        if nom_classe and nom_classe in self.definitions:
            schema = self.definitions[nom_classe]
            champs_possibles = schema["all"]
            champs_obligatoires = schema["required"]

            args_fournis = set()

            # 1. Vérifier les arguments fournis
            for keyword in node.keywords:
                arg_name = keyword.arg
                args_fournis.add(arg_name)

                if arg_name not in champs_possibles:
                    self.violations.append(
                        f"⛔ Champ INCONNU '{arg_name}' dans '{nom_classe}' "
                        f"(Valides : {list(champs_possibles)})"
                    )

            # 2. Vérifier les arguments manquants
            # Note : On ne peut vérifier ça que si l'instanciation est purement par mot-clé (keyword)
            # Si des args positionnels sont utilisés (ex: Class(1, 2)), l'AST est plus dur à mapper.
            # Mais comme on utilise des dataclasses, les keywords sont la norme.
            if not node.args:  # Si pas d'arguments positionnels
                manquants = champs_obligatoires - args_fournis
                if manquants:
                    self.violations.append(
                        f"⚠️ Champ OBLIGATOIRE manquant dans '{nom_classe}' : {list(manquants)}"
                    )

        self.generic_visit(node)


class FunctionHygieneVisitor(ast.NodeVisitor):
    """
    Analyse l'hygiène interne des fonctions.
    [MODIFIE] : Ne vérifie plus la complexité (Refactor suggéré).
    Vérifie uniquement les variables mortes (Dead Code).
    """

    def __init__(self):
        self.violations = []

    def visit_FunctionDef(self, node):
        """
        Analyse une fonction spécifique isolément.
        """
        # 1. Recensement
        assigned_vars = set()
        used_vars = set()

        # On parcourt tout le corps de la fonction
        for child in ast.walk(node):
            if isinstance(child, ast.Name):
                var_name = child.id

                # On ignore les 'self', les imports globaux supposés, et les underscores
                if var_name == "self" or var_name.startswith("_"):
                    continue

                if isinstance(child.ctx, ast.Store):
                    assigned_vars.add(var_name)
                elif isinstance(child.ctx, ast.Load):
                    used_vars.add(var_name)

        # 2. Analyse des "Variables Fantômes" (Créées mais jamais lues)
        # On ne garde que celles qui ont été assignées localement ET jamais lues
        unused = assigned_vars - used_vars

        # Filtre de sécurité : Parfois une variable est utilisée dans une f-string ou autre
        # L'AST le voit généralement bien, mais on reste prudent sur les arguments
        args_names = {arg.arg for arg in node.args.args}
        unused = unused - args_names

        if unused:
            self.violations.append(
                f"⚠️ HYGIÈNE '{node.name}' : Variables mortes -> {list(unused)}"
            )

        self.generic_visit(node)


class ShadowComplianceVisitor(ast.NodeVisitor):
    """
    POLICE DE STANDARDISATION :
    Détecte les dictionnaires manuels qui ressemblent étrangement à des Dataclasses existantes.
    But : Forcer l'utilisation des objets standards.
    """

    def __init__(self, definitions_contrats: Dict[str, Set[str]]):
        self.definitions = definitions_contrats
        self.violations = []

    def _analyser_dictionnaire(self, node_dict: ast.Dict, contexte: str):
        """
        Compare les clés d'un dictionnaire AST avec les définitions officielles.
        """
        # 1. Extraire les clés du dictionnaire (seulement les strings constantes)
        cles_trouvees = set()
        for key in node_dict.keys:
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                cles_trouvees.add(key.value)

        if not cles_trouvees:
            return

        # 2. Shadow Matching : Comparer avec chaque contrat officiel
        for nom_contrat, champs_contrat in self.definitions.items():
            # On cherche une intersection significative
            intersection = cles_trouvees.intersection(champs_contrat)

            # CRITÈRE DE DÉTECTION :
            # Si le dictionnaire contient plus de 50% des champs d'un contrat
            # OU s'il contient exactement les mêmes champs
            ratio = len(intersection) / len(champs_contrat) if champs_contrat else 0

            # On ignore les petits dicts génériques (moins de 2 champs matchés) pour éviter le bruit
            if len(intersection) >= 2 and ratio > 0.6:
                self.violations.append(
                    f"🕵️ DETECTÉ dans {contexte} : Utilisation d'un dictionnaire manuel "
                    f"qui imite le contrat '{nom_contrat}'.\n"
                    f"   -> Clés suspectes : {list(intersection)}\n"
                    f"   -> Conseil : Instanciez directement '{nom_contrat}(...)'."
                )

    def visit_Return(self, node):
        """Vérifie si on retourne un dictionnaire manuel au lieu d'un objet."""
        if isinstance(node.value, ast.Dict):
            self._analyser_dictionnaire(node.value, contexte="return")
        self.generic_visit(node)

    def visit_Assign(self, node):
        """Vérifie si on assigne un dictionnaire manuel imitant un objet."""
        if isinstance(node.value, ast.Dict):
            # On essaie de récupérer le nom de la variable pour le log
            nom_var = "variable inconnue"
            if node.targets and isinstance(node.targets[0], ast.Name):
                nom_var = node.targets[0].id

            self._analyser_dictionnaire(
                node.value, contexte=f"assignation de '{nom_var}'"
            )
        self.generic_visit(node)


class AgentAuditor(AgentBase):
    def __init__(self):
        super().__init__(nom_agent="AgentAuditor")
        """
        Superviseur de la qualité et de la sécurité du système.

        Cette classe centralise toutes les logiques de vérification. Elle est conçue pour être
        exécutée de manière asynchrone (Daemon) ou ponctuelle (CI/CD check).
        Elle dispose d'un droit de regard sur tous les fichiers du projet et d'un canal
        privilégié pour signaler les alertes critiques au "Gardien" (Logger Governance).

        Attributes:
            sanctuaires (List[str]): Liste des dossiers protégés contre l'écriture destructive.
            vocabulaire_officiel (Set[str]): Ensemble des termes valides définis dans les contrats d'interface.
        """

        # 1. Chargement Config (Source de vérité)
        self.config_file = Path(__file__).parent / "config_agent_auditor.yaml"
        self.config = self._charger_config()

        # 2. Assignation dynamique depuis le YAML
        cfg_secu = self.config.get("securite", {})
        self.sanctuaires = cfg_secu.get("sanctuaires", [])
        self.patterns_interdits = cfg_secu.get("patterns_interdits", [])

        cfg_vocab = self.config.get("vocabulaire", {})
        self.whitelist_vars = set(cfg_vocab.get("exceptions_autorisees", []))

        self.seuil_alerte = self.config.get("communication", {}).get(
            "seuil_alerte_gardien", "CRITIQUE"
        )

        # Récupération du chemin du registre d'encodage (plus de variable globale en dur)
        self.registry_path = Path(
            self.config.get("configuration", {}).get(
                "chemin_registre_encodage",
                "D:/rag_personnel/agentique/sous_agents_gouvernes/agent_Auditor/auditor_encoding_registry.json",
            )
        )

        self.vocabulaire_officiel = self._construire_vocabulaire_contrats()
        self.logger.info(f"🕵️ AgentAuditor prêt via YAML.")

    def _collecter_violations_runtime(self) -> List[Dict]:
        """
        Lit le fichier journal généré par auditor_base.py lors de l'exécution des agents.
        Permet d'inclure les erreurs dynamiques dans le rapport statique.
        """
        log_path = self.auditor.get_path("logs")
        if not log_path:
            return []

        target_file = Path(log_path) / "runtime_violations.jsonl"
        violations = []

        if target_file.exists():
            try:
                with open(target_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            violations.append(json.loads(line))
            except Exception as e:
                self.logger.log_error(f"Erreur lecture runtime logs: {e}")

        return violations

    def _charger_config(self) -> Dict:
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f)
            except Exception:
                pass
        return {}

    def _construire_definitions_contrats(self) -> Dict[str, Dict[str, Set[str]]]:
        """
        Construit un registre riche :
        { 'NomClasse': {'all': {'champ1', 'champ2'}, 'required': {'champ1'}} }
        """
        defs = {}
        for name, obj in inspect.getmembers(contrats):
            if inspect.isclass(obj) and hasattr(obj, "__dataclass_fields__"):
                all_fields = set(obj.__dataclass_fields__.keys())
                required_fields = set()

                # Inspection pour trouver les champs sans valeur par défaut
                # C'est la seule façon fiable de savoir ce qui est "obligatoire"
                try:
                    signature = inspect.signature(obj)
                    for param_name, param in signature.parameters.items():
                        if param.default == inspect.Parameter.empty:
                            required_fields.add(param_name)
                except Exception:
                    # Fallback si l'inspection échoue (ex: certains objets dynamiques)
                    pass

                defs[name] = {"all": all_fields, "required": required_fields}
        return defs

    def auditer_compliance_contrats(self, fichier: Path) -> List[str]:
        """
        Police des Interfaces (AST Visitor).

        Vérifie statiquement que chaque instanciation d'une Dataclass du système
        respecte strictement sa signature officielle.
        Détecte :
        - Les champs obligatoires manquants.
        - Les champs inventés/inconnus (typos).

        Cela empêche les erreurs "silencieuses" où une donnée critique est perdue
        parce que le développeur a mal nommé un argument.
        """
        if fichier.suffix != ".py":
            return []

        try:
            code = fichier.read_text(encoding="utf-8")
            tree = ast.parse(code)

            # On charge la vérité à l'instant T
            definitions = self._construire_definitions_contrats()

            visitor = ContractComplianceVisitor(definitions)
            visitor.visit(tree)

            return visitor.violations

        except Exception as e:
            return [f"Erreur AST Compliance : {e}"]

    def _construire_vocabulaire_contrats(self) -> Set[str]:
        """
        Scanne contrats_interface.py pour extraire tous les noms de champs valides.
        C'est la référence absolue.
        """
        vocab = set()
        # 1. Inspection des Dataclasses
        for _, obj in inspect.getmembers(contrats):
            if inspect.isclass(obj) and hasattr(obj, "__dataclass_fields__"):
                for field_name in obj.__dataclass_fields__:
                    vocab.add(field_name)
        return vocab

    def _signaler_au_gardien(self, message: str, niveau: str):
        """
        Communication directe avec le Gardien si une règle critique est violée.
        """
        # On ne signale que si le niveau est égal ou supérieur au seuil (ex: CRITIQUE)
        if niveau == "CRITIQUE" or (
            niveau == "MAJEUR" and self.seuil_alerte == "MAJEUR"
        ):
            if hasattr(self.logger, "signal_gouvernance"):
                self.logger.signal_gouvernance(
                    f"🚨 AUDITOR ALERTE [{niveau}] : {message}"
                )
            else:
                self.logger.log_warning(
                    f"🚨 AUDITOR ALERTE (Pas de lien Gardien) : {message}"
                )

    def valider_utilisation_complete_dataclass(self, objet_a_valider: Any) -> bool:
        """
        Audit Runtime d'Utilisation des Données.

        Vérifie, au moment de l'exécution, que tous les champs d'un objet de contexte
        (ex: `StandardPrompt`) ont bien été lus/consommés par l'AgentParole.

        Permet de détecter les bugs logiques où une information est récupérée (coût CPU/IO)
        mais jamais injectée dans le prompt final (Information Perdue), ce qui est invisible statiquement.
        """
        # 1. Vérification défensive : Est-ce que la méthode existe ?
        if not hasattr(objet_a_valider, "get_unused_fields"):
            # Ce n'est pas un objet trackable par l'Auditor (ou le Mixin est absent)
            # On ne bloque pas l'exécution.
            return True

        try:
            # 2. Appel sécurisé
            unused = objet_a_valider.get_unused_fields()

            # 3. Récupération du nom de la classe
            if hasattr(objet_a_valider, "get_class_name"):
                class_name = objet_a_valider.get_class_name()  # Wrapper
            else:
                class_name = objet_a_valider.__class__.__name__  # Mixin direct

            if unused:
                unused_list = sorted(list(unused))
                self.logger.log_warning(
                    f"⚠️ Dataclass '{class_name}' a des champs ignorés/vides : {unused_list}"
                )
                if len(unused) > 2:
                    self._signaler_au_gardien(
                        f"Agent Parole ignore {len(unused)} champs de '{class_name}'",
                        "MAJEUR",
                    )
                # Nouveau contrôle pour vérifier que les listes ne sont pas vides
                for field_name in unused:
                    value = getattr(objet_a_valider, field_name)
                    if isinstance(value, list) and not value:
                        self.logger.log_error(
                            f"❌ Champ '{field_name}' est une liste vide dans '{class_name}'"
                        )
                        return False
                    elif isinstance(value, (str, dict)) and not value:
                        self.logger.log_error(
                            f"❌ Champ '{field_name}' est une chaîne vide ou un dictionnaire vide dans '{class_name}'"
                        )
                        return False

                return False

            self.logger.log_thought(
                f"✅ Dataclass '{class_name}' - Validée (Champs complets)"
            )
            return True

        except Exception as e:
            self.logger.log_error(f"Erreur validation runtime dataclass : {e}")
            return True  # On ne bloque pas l'exécution pour une erreur d'audit

    def valider_format_entree_strict(self, data: Any, format_attendu: str) -> bool:
        """
        Valide strictement qu'une entrée est bien une dataclass du bon type.
        Bloque si None ou mauvais type.

        Args:
            data: Données reçues
            format_attendu: Nom de la dataclass attendue (ex: "StandardPrompt")

        Returns:
            True si valide

        Raises:
            TypeError si le type est invalide
        """
        from dataclasses import is_dataclass

        # Vérifier que ce n'est pas None
        if data is None:
            raise TypeError(f"❌ ERREUR CONTRAT: Reçu None au lieu de {format_attendu}")

        # Vérifier que c'est une dataclass
        if not is_dataclass(data):
            raise TypeError(
                f"❌ ERREUR CONTRAT: Reçu {type(data).__name__} au lieu de dataclass {format_attendu}"
            )

        # Vérifier que c'est la bonne dataclass
        if data.__class__.__name__ != format_attendu:
            raise TypeError(
                f"❌ ERREUR CONTRAT: Reçu dataclass {data.__class__.__name__} au lieu de {format_attendu}"
            )

        return True

    # =========================================================================
    # SECTION 1 : AUDIT DATAS & SÉCURITÉ (Le Gardien)
    # =========================================================================

    def auditer_hygiene_interne(self, fichier: Path) -> List[str]:
        """
        Nouveau module : Vérifie la propreté interne des fonctions (Code mort).
        NOTE: Ne vérifie plus la complexité cognitive.
        """
        if fichier.suffix != ".py":
            return []

        try:
            code = fichier.read_text(encoding="utf-8")
            tree = ast.parse(code)

            # ✅ CORRECTION : On instancie sans argument
            # (On ne lit plus le seuil de complexité car on ne l'utilise plus)
            visitor = FunctionHygieneVisitor()
            visitor.visit(tree)

            return visitor.violations

        except Exception as e:
            return [f"Erreur AST Hygiène : {e}"]

    def auditer_securite_fichier(self, fichier: Path) -> List[str]:
        """
        Scanner de Sécurité Préventif.

        Analyse le code source pour identifier des opérations I/O dangereuses
        sur des zones sensibles ("Sanctuaires").

        Intelligence :
        Capable de distinguer une attaque destructive (ex: `shutil.rmtree` sur /memoire)
        d'une opération de maintenance légitime (ex: rotation de logs) grâce à
        l'analyse contextuelle des mots-clés environnants ("backup", "rotation").
        """
        try:
            content = fichier.read_text(encoding="utf-8", errors="replace")
            alerts = []

            # A. Sanctuaires
            for zone in self.sanctuaires:
                if zone in content:
                    # Détection d'une commande destructive
                    if re.search(r"\.unlink|\.remove|rmtree", content):
                        # --- EXCEPTION : ROTATION DE BACKUPS ---
                        # Si le fichier contient des preuves de logique de sauvegarde (copy + delete)
                        # On considère l'opération comme une maintenance légitime.
                        marqueurs_backup = [
                            "shutil.copy",
                            "backup",
                            "rotation",
                            "archive",
                            "_old",
                        ]
                        # On vérifie si au moins un marqueur est présent dans le fichier
                        est_rotation_legitime = any(
                            m in content.lower() for m in marqueurs_backup
                        )

                        if est_rotation_legitime:
                            # On ignore l'alerte (ou on pourrait logger un INFO silencieux)
                            continue
                        # ---------------------------------------

                        msg = f"Code destructif sur sanctuaire '{zone}' dans {fichier.name}"
                        alerts.append(f"CRITIQUE: {msg}")
                        self._signaler_au_gardien(msg, "CRITIQUE")

            # B. Patterns (Reste inchangé)
            for pat in self.patterns_interdits:
                if re.search(pat["pattern"], content):
                    msg = f"{pat['message']} dans {fichier.name}"
                    niveau = pat.get("gravite", "ALERTE")
                    alerts.append(f"{niveau}: {msg}")
                    self._signaler_au_gardien(msg, niveau)

            return alerts
        except Exception:
            return []

    def auditer_standardisation(self, fichier: Path) -> List[str]:
        """
        Chasseur d'Objets Fantômes (Shadow Objects).

        Détecte les développeurs qui utilisent des dictionnaires (`{}`) pour simuler
        des objets du système au lieu d'instancier les classes officielles.

        Méthode :
        Compare les clés des dictionnaires littéraux avec les schémas des Dataclasses.
        Si un dictionnaire ressemble à >60% à une Dataclass connue (ex: a des clés 'sujet', 'action', 'prompt'),
        il est signalé comme une violation de standardisation.
        """
        if fichier.suffix != ".py":
            return []

        try:
            code = fichier.read_text(encoding="utf-8")
            tree = ast.parse(code)

            # 1. On récupère la structure riche (utilisée par ContractVisitor)
            definitions_riches = self._construire_definitions_contrats()

            # 2. ✅ CORRECTIF : On extrait seulement 'all' pour le ShadowVisitor
            # Le ShadowVisitor ne veut savoir que "quels sont les champs possibles ?"
            definitions_plates = {
                nom: infos["all"] for nom, infos in definitions_riches.items()
            }

            visitor = ShadowComplianceVisitor(definitions_plates)
            visitor.visit(tree)

            return visitor.violations

        except Exception as e:
            return [f"Erreur Standardisation : {e}"]

    # =========================================================================
    # SECTION 2 : AUDIT STRUCTURE & ARCHITECTURE (L'Urbaniste)
    # =========================================================================

    def auditer_conformite_structurelle(self, fichier: Path) -> List[str]:
        """Vérifie l'héritage et les imports."""
        if "agent_" not in fichier.name:
            return []

        alerts = []
        try:
            code = fichier.read_text(encoding="utf-8")
            tree = ast.parse(code)

            # Héritage AgentBase
            has_base = False
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    for base in node.bases:
                        if isinstance(base, ast.Name) and base.id == "AgentBase":
                            has_base = True
            if not has_base:
                alerts.append("Structure: N'hérite pas de AgentBase")

            # Outils universels
            if "self.logger" not in code:
                alerts.append("Structure: Logger non utilisé")

        except Exception:
            pass
        return alerts

    def generer_cartographie(self) -> str:
        """
        Génère la map pour le LLM en respectant STRICTEMENT les exclusions du config.yaml.
        """
        data = {}
        root = ROOT_DIR

        # 1. Chargement config
        targets = self.config.get("perimetre", {}).get(
            "dossiers_cartographie", ["agentique"]
        )
        exclusions = self.config.get("perimetre", {}).get("exclusions_globales", [])

        self.logger.info(
            f"🗺️ Génération cartographie (Exclusions: {len(exclusions)} règles)..."
        )

        count_files = 0
        for t in targets:
            d = root / t
            if d.exists():
                for f in d.rglob("*.py"):
                    # 2. FILTRAGE STRICT
                    # Si le chemin contient un mot interdit (ex: "BACKUP", "venv"), on saute
                    if any(ex in str(f) for ex in exclusions):
                        continue

                    try:
                        rel = f.relative_to(root).as_posix()
                        data[rel] = "Python Script"
                        count_files += 1
                    except:
                        pass

        dest = root / "mapping_structure" / "project_map.json"
        try:
            with open(dest, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            self.logger.info(
                f"🗺️ Cartographie générée : {count_files} fichiers valides (vs {len(list(root.rglob('*.py')))} total)."
            )
            return str(dest)
        except Exception as e:
            self.logger.log_error(f"Erreur génération map: {e}")
            return ""

    # =========================================================================
    # SECTION 3 : AUDIT DE FLUX & SUPERVISION (Le Contrôleur de Gestion)
    # =========================================================================

    def _charger_stats_agent(self, nom_agent_clean: str) -> Dict:
        """
        Charge la section 'dashboard_stats' du fichier config d'un agent.
        Tente de localiser le fichier config de manière robuste.
        """
        # On suppose que config est dans agentique/base/config/ ou agentique/Configs/
        # Ou à la racine de l'agent. On utilise l'AuditorBase pour trouver le chemin si possible
        # Sinon on cherche manuellement.

        try:
            # 1. Essai via le mapping standard (si disponible dans ta structure)
            path_str = self.auditor.get_path("config", nom_agent_clean)
            if path_str and Path(path_str).exists():
                path = Path(path_str)
            else:
                # 2. Recherche brute si le mapping échoue
                # On cherche config_nomagent.yaml dans tout le projet (limité à agentique)
                root = ROOT_DIR / "agentique"
                candidats = list(root.rglob(f"config_{nom_agent_clean}.yaml"))
                if not candidats:
                    return {}
                path = candidats[0]

            # Lecture
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            return data.get("dashboard_stats", {})

        except Exception as e:
            self.logger.log_warning(
                f"⚠️ Impossible de lire les stats pour {nom_agent_clean}: {e}"
            )
            return {}

    def auditer_coherence_flux(self) -> List[str]:
        """
        Contrôle de Gestion des Données (Flux 360°).

        Effectue une réconciliation comptable entre :
        1. **La Production** : Nombre d'appels au Moteur LLM (Source).
        2. **La Sécurisation** : Nombre d'items dans les logs bruts (Tampon).
        3. **La Mémorisation** : Nombre de fichiers dans l'historique (Destination).

        Détecte les fuites de mémoire (ex: Le LLM parle, mais rien n'est sauvegardé)
        et lève des alertes MAJEURES ou CRITIQUES selon l'ampleur de la perte.
        """
        alertes = []

        # Récupération des seuils depuis le YAML
        seuils_cfg = self.config.get("analyse", {}).get("seuils", {})
        tolerance = seuils_cfg.get("flux_tolerance_pourcent", 0.05)
        min_alerte = seuils_cfg.get("flux_min_alerte", 5)

        # --- 1. SOURCE : PRODUCTION LLM ---
        stats_llm = self._charger_stats_agent("moteurllm")
        spec_llm = stats_llm.get("specifiques", {})
        total_llm = spec_llm.get("appels_generer_stream", 0) + spec_llm.get(
            "appels_generer", 0
        )

        # --- 2. CIBLE A : SAUVEGARDE BRUTE (Append/Journalier) ---
        chemin_brute = self.auditor.get_path("brute", nom_agent="memoire")
        nb_items_brute = 0
        if chemin_brute and Path(chemin_brute).exists():
            try:
                for f in Path(chemin_brute).glob("*.json"):
                    try:
                        content = f.read_text(encoding="utf-8").strip()
                        if not content:
                            continue

                        # Détection intelligente : Liste ou JSONL
                        if content.startswith("["):
                            nb_items_brute += len(
                                json.loads(content)
                            )  # Liste journalière
                        elif content.startswith("{"):
                            # Soit un objet unique, soit du JSONL
                            lignes = [l for l in content.splitlines() if l.strip()]
                            nb_items_brute += len(
                                lignes
                            )  # 1 ligne = 1 item (ou 1 objet seul)
                    except Exception:
                        pass
            except Exception as e:
                self.logger.log_warning(f"Scan Brute impossible: {e}")

        # --- 3. CIBLE B : MÉMOIRE HISTORIQUE (1 Fichier = 1 Interaction) ---
        chemin_hist = self.auditor.get_path("historique", nom_agent="memoire")
        nb_fichiers_hist = 0
        if chemin_hist and Path(chemin_hist).exists():
            # Ici, la règle est stricte : 1 interaction = 1 fichier .json
            nb_fichiers_hist = len(list(Path(chemin_hist).glob("interaction_*.json")))

        # Analyse des écarts avec les seuils dynamiques
        seuil_dynamique = max(min_alerte, total_llm * tolerance)

        # CHECK 1 : Perte de données brutes (CRITIQUE)
        delta_brute = total_llm - nb_items_brute
        if delta_brute > seuil_dynamique:
            msg = (
                f"📉 FUITE BRUTE (CRITIQUE) : Le LLM a généré {total_llm} fois, "
                f"mais seuls {nb_items_brute} items sont sécurisés dans '/brute'."
            )
            self._signaler_au_gardien(msg, "CRITIQUE")
            alertes.append(msg)

        # CHECK 2 : Amnésie Mémoire (MAJEUR)
        delta_hist = total_llm - nb_fichiers_hist
        if delta_hist > seuil_dynamique:
            msg = (
                f"🧠 AMNÉSIE (MAJEUR) : Le LLM a généré {total_llm} fois, "
                f"mais seuls {nb_fichiers_hist} souvenirs existent dans '/historique'."
            )
            self._signaler_au_gardien(msg, "MAJEUR")
            alertes.append(msg)

        self.logger.info(
            f"📊 Flux: LLM({total_llm}) -> Brute({nb_items_brute}) -> Hist({nb_fichiers_hist})"
        )
        return alertes

    # =========================================================================
    # SECTION 4 : AUDIT D'ENCODAGE & STANDARDS DE FICHIERS (Le Bibliothécaire)
    # =========================================================================

    def auditer_encodage_fichiers(
        self,
        dossiers_a_verifier: Optional[List[str]] = None,
        max_files: Optional[int] = 500,
        check_standards: bool = True,
    ) -> Dict[str, Any]:
        """
        Bibliothécaire du Système (Hygiène de Fichiers).

        Assure que tous les fichiers texte du projet respectent les normes POSIX :
        - Encodage UTF-8 strict.
        - Présence d'une nouvelle ligne en fin de fichier (EOF newline).
        - Absence d'espaces en fin de ligne (Trailing whitespace).

        Utilise un registre persistant (cache) pour ne scanner que les fichiers modifiés,
        garantissant une performance optimale même sur des milliers de fichiers.
        """

        violations = []
        fichiers_verifies = 0
        fichiers_skipped = 0

        reg = self._load_encoding_registry()
        now_ts = int(time.time())

        if dossiers_a_verifier is None:
            dossiers_a_verifier = [
                "historique",
                "persistante",
                "reflexive",
                "regles",
                "connaissances",
                "modules_formation",
                "feedback",
            ]

        enc_cfg = self.config.get("analyse", {}).get("encodage", {})

        # Priorité : Argument > YAML > Liste vide
        dossiers_a_verifier = dossiers_a_verifier or enc_cfg.get(
            "dossiers_a_verifier", []
        )
        max_files = enc_cfg.get("max_fichiers_par_scan", 500)
        check_standards = enc_cfg.get("check_standards_vsc", True)

        # Utilisation de self.registry_path défini dans __init__
        reg = self._load_encoding_registry()

        # 2. Scanner chaque dossier
        for type_memoire in dossiers_a_verifier:
            chemin = self.auditor.get_path(type_memoire, nom_agent="memoire")
            if not chemin:
                continue

            dossier = Path(chemin)
            if not dossier.exists():
                continue

            # Protection: ne pas auditer Archives/ si ça peut être dans tes paths
            if "Archives" in str(dossier):
                continue

            # 3. Vérifier tous les fichiers texte
            for fichier in dossier.rglob("*"):
                if max_files is not None and fichiers_verifies >= max_files:
                    break

                if not fichier.is_file():
                    continue
                if not self._is_text_ext(fichier):
                    continue

                key = str(fichier).replace("\\", "/")

                try:
                    fp = self._fingerprint(fichier)
                    prev = reg.get(key)

                    # SKIP si inchangé (mtime + size)
                    if (
                        prev
                        and prev.get("mtime") == fp["mtime"]
                        and prev.get("size") == fp["size"]
                    ):
                        fichiers_skipped += 1
                        continue

                    # --- UTF-8 rapide (ne lit pas tout) ---
                    self._quick_utf8_check(fichier)

                    # Si on ne veut pas les standards, on s'arrête ici (très rapide)
                    if not check_standards:
                        reg[key] = {
                            "mtime": fp["mtime"],
                            "size": fp["size"],
                            "status": "ok_utf8",
                            "checked_at": now_ts,
                        }
                        fichiers_verifies += 1
                        continue

                    # --- Standards: lire complet uniquement pour les fichiers CHANGÉS ---
                    with open(fichier, "r", encoding="utf-8") as f:
                        contenu = f.read()

                    # newline finale
                    if contenu and not contenu.endswith("\n"):
                        violations.append(
                            {
                                "fichier": str(fichier),
                                "type": "NEWLINE_MANQUANTE",
                                "message": "Fichier ne se termine pas par \\n",
                            }
                        )

                    # trailing whitespace (limiter le coût si énorme fichier)
                    lignes_avec_trailing = []
                    for i, ligne in enumerate(contenu.splitlines(), 1):
                        if ligne.endswith((" ", "\t")):
                            lignes_avec_trailing.append(i)
                            if len(lignes_avec_trailing) >= 50:  # plafond interne
                                break

                    if lignes_avec_trailing:
                        violations.append(
                            {
                                "fichier": str(fichier),
                                "type": "TRAILING_WHITESPACE",
                                "message": f"Espaces en fin de ligne: {lignes_avec_trailing[:5]}",
                            }
                        )

                    reg[key] = {
                        "mtime": fp["mtime"],
                        "size": fp["size"],
                        "status": "ok_utf8",
                        "checked_at": now_ts,
                    }
                    fichiers_verifies += 1

                except UnicodeDecodeError as e:
                    violations.append(
                        {
                            "fichier": str(fichier),
                            "type": "ENCODAGE_INVALIDE",
                            "message": f"Fichier non UTF-8: {str(e)}",
                        }
                    )
                    # On enregistre quand même le fingerprint pour éviter de rebloquer
                    try:
                        fp = self._fingerprint(fichier)
                        reg[key] = {
                            "mtime": fp["mtime"],
                            "size": fp["size"],
                            "status": "bad_utf8",
                            "error": str(e),
                            "checked_at": now_ts,
                        }
                    except Exception:
                        pass
                    fichiers_verifies += 1

                except Exception as e:
                    violations.append(
                        {
                            "fichier": str(fichier),
                            "type": "ERREUR_LECTURE",
                            "message": str(e),
                        }
                    )
                    try:
                        fp = self._fingerprint(fichier)
                        reg[key] = {
                            "mtime": fp["mtime"],
                            "size": fp["size"],
                            "status": "error",
                            "error": str(e),
                            "checked_at": now_ts,
                        }
                    except Exception:
                        pass
                    fichiers_verifies += 1

        self._save_encoding_registry(reg)

        rapport = {
            "fichiers_verifies": fichiers_verifies,
            "fichiers_skipped": fichiers_skipped,
            "nb_violations": len(violations),
            "violations": violations,
            "conforme": len(violations) == 0,
        }

        if violations:
            self.logger.log_warning(
                f"⚠️ Audit encodage: {len(violations)} violation(s) "
                f"sur {fichiers_verifies} fichiers (skipped: {fichiers_skipped})"
            )
            for v in violations[:10]:
                self.logger.log_warning(f"  - {v['type']}: {v['fichier']}")
        else:
            self.logger.info(
                f"✅ Audit encodage: {fichiers_verifies} fichiers vérifiés "
                f"(skipped: {fichiers_skipped})"
            )

        return rapport

    def corriger_encodage_fichier(self, fichier_path: str) -> bool:
        """
        Corrige automatiquement l'encodage d'un fichier:
        - Force UTF-8
        - Ajoute newline finale
        - Retire trailing whitespace

        Returns:
            True si corrections appliquées, False sinon
        """
        try:
            fichier = Path(fichier_path)

            # 1. Lire le contenu (essayer plusieurs encodages)
            contenu = None
            for encoding in ["utf-8", "latin-1", "cp1252"]:
                try:
                    with open(fichier, "r", encoding=encoding) as f:
                        contenu = f.read()
                    break
                except UnicodeDecodeError:
                    continue

            if contenu is None:
                self.logger.log_error(f"❌ Impossible de décoder: {fichier}")
                return False

            # 2. Appliquer les corrections
            corrections_appliquees = False

            # A. Trailing whitespace
            lignes_corrigees = [ligne.rstrip() for ligne in contenu.splitlines()]
            contenu_corrige = "\n".join(lignes_corrigees)

            original_normalized = contenu.replace("\r\n", "\n").replace("\r", "\n")
            if contenu_corrige != original_normalized:
                corrections_appliquees = True
                corrections_appliquees = True

            # B. Newline finale
            if contenu_corrige and not contenu_corrige.endswith("\n"):
                contenu_corrige += "\n"
                corrections_appliquees = True

            # 3. Réécrire en UTF-8
            if corrections_appliquees:
                with open(fichier, "w", encoding="utf-8", newline="\n") as f:
                    f.write(contenu_corrige)
                self.logger.info(f"✅ Corrigé: {fichier}")
                return True

            return False

        except Exception as e:
            self.logger.log_error(f"❌ Erreur correction {fichier_path}: {e}")
            return False

    def corriger_tous_encodages(
        self, dossiers: Optional[List[str]] = None
    ) -> Dict[str, int]:
        """
        Lance la correction automatique sur tous les fichiers non conformes.

        Returns:
            Dict avec stats: {'fichiers_corriges': N, 'erreurs': M}
        """
        # 1. Audit pour trouver les violations
        rapport = self.auditer_encodage_fichiers(dossiers)

        fichiers_a_corriger = set()
        for v in rapport["violations"]:
            fichiers_a_corriger.add(v["fichier"])

        # 2. Correction
        stats = {"fichiers_corriges": 0, "erreurs": 0}

        for fichier in fichiers_a_corriger:
            if self.corriger_encodage_fichier(fichier):
                stats["fichiers_corriges"] += 1
            else:
                stats["erreurs"] += 1

        self.logger.info(
            f"📝 Correction encodage terminée: {stats['fichiers_corriges']} fichiers corrigés, "
            f"{stats['erreurs']} erreurs"
        )

        return stats

    # REGISTRE ENCODAGE (PERSISTANT) + SCAN INCRÉMENTAL
    def _load_encoding_registry(self) -> Dict[str, Any]:
        try:
            if ENCODING_REGISTRY_PATH.exists():
                with open(ENCODING_REGISTRY_PATH, "r", encoding="utf-8") as f:
                    return json.load(f) or {}
        except Exception:
            pass
        return {}

    def _save_encoding_registry(self, reg: Dict[str, Any]) -> None:
        try:
            ENCODING_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp = ENCODING_REGISTRY_PATH.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(reg, f, ensure_ascii=False, indent=2)
            tmp.replace(ENCODING_REGISTRY_PATH)
        except Exception:
            pass

    def _fingerprint(self, fichier: Path) -> Dict[str, int]:
        st = fichier.stat()
        return {"mtime": int(st.st_mtime), "size": int(st.st_size)}

    def _is_text_ext(self, fichier: Path) -> bool:
        return fichier.suffix.lower() in {
            ".json",
            ".jsonl",
            ".md",
            ".txt",
            ".yaml",
            ".yml",
            ".py",
        }

    def _quick_utf8_check(self, fichier: Path, max_bytes: int = 64 * 1024) -> None:
        # Valide utf-8 rapidement sans lire tout le fichier
        raw = fichier.read_bytes()[:max_bytes]
        raw.decode("utf-8")  # strict

    # ================================================================
    # POINT D'ENTRÉE GLOBAL
    # ================================================================
    def auditer_systeme(self, mode="sanity_check") -> Dict:
        """
        Point d'entrée de l'Audit Global (The Big Scan).

        Orchestre une batterie de tests complets :
        1. **Audit Sécurité** : Recherche de patterns dangereux (rmtree, unlink).
        2. **Audit Structurel** : Vérification de l'héritage et des imports.
        3. **Audit Hygiène** : Détection de code mort via AST.
        4. **Audit Contrats** : Validation des instanciations de Dataclasses.
        5. **Audit Standardisation** : Chasse aux dictionnaires manuels (Shadow Objects).
        6. **Supervision Flux** : Réconciliation comptable entre le LLM et la Mémoire.
        7. **Analyse Runtime** : Injection des erreurs détectées pendant l'exécution (logs).

        Génère un rapport JSON complet (`audit_report.json`) et met à jour la cartographie.

        Args:
            mode (str): Niveau de profondeur ("sanity_check" ou "deep_scan").

        Returns:
            Dict: Le rapport d'audit structuré contenant toutes les alertes.
        """
        # 1. Gestion du mode via Config
        if mode is None:
            mode = self.config.get("configuration", {}).get(
                "mode_par_defaut", "sanity_check"
            )

        self.logger.info(f"🚀 Démarrage Audit Système (Mode: {mode})")

        rapport = {"timestamp": datetime.now().isoformat(), "fichiers": []}
        root = ROOT_DIR

        # 1. Récupération des cibles (Liste Blanche)
        dossiers_cibles = self.config.get("perimetre", {}).get(
            "dossiers_audit", ["agentique"]
        )
        exclusions = self.config.get("perimetre", {}).get("exclusions_globales", [])

        files = []
        # On ne scanne QUE les dossiers demandés
        for dossier_nom in dossiers_cibles:
            dossier_path = root / dossier_nom
            if dossier_path.exists():
                # On récupère tous les .py du dossier
                fichiers_dossier = list(dossier_path.rglob("*.py"))
                self.logger.info(
                    f"📂 Scan dossier '{dossier_nom}' : {len(fichiers_dossier)} fichiers détectés."
                )
                files.extend(fichiers_dossier)
            else:
                self.logger.log_warning(f"⚠️ Dossier cible introuvable : {dossier_path}")

        # 2. Filtrage (Exclusions locales)
        files = [f for f in files if not any(ex in str(f) for ex in exclusions)]

        # 3. Exécution de l'audit fichier par fichier
        for f in files:
            try:
                res_fichier = {
                    "nom": f.name,
                    "path": str(f.relative_to(root)),
                    "alertes": [],
                }

                # Sécurité (Toujours)
                res_fichier["alertes"].extend(self.auditer_securite_fichier(f))
                # Structure (Toujours pour les agents)
                res_fichier["alertes"].extend(self.auditer_conformite_structurelle(f))
                # Vérification de l'hygiène interne
                res_fichier["alertes"].extend(self.auditer_hygiene_interne(f))
                # Vérification des Contrats
                res_fichier["alertes"].extend(self.auditer_compliance_contrats(f))

                # Vocabulaire
                res_fichier["alertes"].extend(self.auditer_standardisation(f))

                if res_fichier["alertes"]:
                    rapport["fichiers"].append(res_fichier)

            except Exception as e:
                self.logger.log_error(f"Erreur audit fichier {f.name}: {e}")

        # ==========================================
        # ✅ AJOUT : AUDIT DE SUPERVISION GLOBAL (Hors de la boucle)
        # ==========================================
        self.logger.info("🧠 Démarrage Audit Supervision Flux...")
        try:
            alertes_flux = self.auditer_coherence_flux()

            if alertes_flux:
                # On ajoute ces alertes au rapport global dans une section "SYSTEM"
                res_flux = {
                    "nom": "SUPERVISION_FLUX",
                    "path": "SYSTEM",
                    "alertes": alertes_flux,
                }
                rapport["fichiers"].append(res_flux)

                for a in alertes_flux:
                    self.logger.log_warning(f"🚨 {a}")
            else:
                self.logger.info("✅ Cohérence des flux validée (LLM == Mémoire).")
        except Exception as e:
            self.logger.log_error(f"Erreur lors de l'audit de flux: {e}")
        # ==========================================
        # ✅ AJOUT : INJECTION DES VIOLATIONS RUNTIME
        # ==========================================
        self.logger.info("🧠 Intégration des violations Runtime (AuditorBase)...")
        runtime_errors = self._collecter_violations_runtime()

        if runtime_errors:
            # On ajoute une section spéciale dans le rapport
            rapport["runtime_analysis"] = {
                "status": "ALERTES DÉTECTÉES",
                "count": len(runtime_errors),
                "details": runtime_errors,
            }
            # On peut aussi les réinjecter dans le compteur global d'alertes
            for err in runtime_errors:
                self.logger.log_warning(
                    f"🚨 [RUNTIME PREUVES] {err['agent_source']} : {err['message']}"
                )
        else:
            rapport["runtime_analysis"] = {"status": "CLEAN", "count": 0}

        # 4. Cartographie & Sauvegarde
        self.generer_cartographie()

        p_rap = Path(self.auditor.get_path("logs")) / "audit_report.json"
        try:
            with open(p_rap, "w", encoding="utf-8") as f:
                json.dump(rapport, f, indent=2)
        except Exception as e:
            self.logger.log_error(f"Erreur sauvegarde rapport: {e}")

        nb_alertes = sum(len(f["alertes"]) for f in rapport["fichiers"])

        # Injection des clés manquantes dans le rapport
        rapport["nb_fichiers"] = len(files)
        rapport["nb_alertes"] = nb_alertes

        if nb_alertes > 0:
            self.logger.log_warning(
                f"⚠️ Audit terminé : {nb_alertes} alertes sur {len(files)} fichiers (incluant supervision)."
            )
        else:
            self.logger.info(
                f"✅ Audit terminé : Système Sain ({len(files)} fichiers)."
            )

        return rapport


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO)
    auditor = AgentAuditor()
    print("🧪 Test Mode Deep Scan...")
    auditor.auditer_systeme(mode="deep_scan")
