#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Analyseur de code V2 - Enrichi avec graphe d'appels détaillé
=============================================================
Module "Worker" responsable de la transformation du code source en données structurées pour le RAG.

Ce module implémente une chaîne de traitement (Pipeline) sophistiquée :
1.  **Scan Récursif** : Parcours du projet avec filtrage intelligent (Blacklist .git, venv).
2.  **Analyse Statique (AST)** : Parsing profond de chaque fichier Python pour extraire :
    - Signatures complètes (avec types).
    - Docstrings et commentaires.
    - Attributs de classe (pour résoudre les dépendances `self.xxx`).
    - Graphe d'appels (Qui appelle Qui ?).
3.  **Chunking Sémantique** : Découpage du code en unités logiques (Classes, Méthodes, Fonctions) plutôt qu'en blocs de texte arbitraires.
4.  **Vectorisation** : Création d'embeddings via Sentence-BERT et indexation FAISS.
5.  **Synthèse** : Génération d'une vue "Squelette" allégée pour le contexte LLM.

Rôle Architectural :
    C'est le moteur "Batch" qui tourne en arrière-plan (ou à la demande) pour maintenir
    la carte du territoire (AgentCode) synchronisée avec le terrain (Fichiers).
"""

import sys
import json
import os
import ast
import yaml
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import asdict
from agentique.base.META_agent import AgentBase
from agentique.base.contrats_interface import ContexteCode
import faiss
from sentence_transformers import SentenceTransformer


class MoteurVecteurCode(AgentBase):
    def __init__(self):
        super().__init__(nom_agent="MoteurVecteurCode")
        """
        Moteur d'indexation lourd (Heavy Lifter).

        Cette classe ne répond pas aux requêtes temps réel. Elle est conçue pour scanner,
        analyser et persister l'état du code sur le disque. Elle génère les artefacts
        (JSON, FAISS, TXT) qui seront ensuite chargés en RAM par l'AgentCode pour la lecture rapide.

        Attributes:
            root_projet (Path): Racine physique du code à scanner.
            output_* (Path): Chemins de destination pour les artefacts générés.
        """

        # --- 1. Infrastructure (Via Auditor) ---
        self.root_projet = Path(self.auditor.get_path("root"))
        self.path_memoire = Path(self.auditor.get_path("memoire"))
        self.path_config_dir = Path(self.auditor.get_path("config"))

        # --- 2. Chargement Config & Chemins ---
        self.config_data = self._charger_config()
        outputs = self.config_data.get("output_paths", {})

        # Chemins absolus basés sur la mémoire de l'Auditor
        self.output_arch = self.path_memoire / outputs.get(
            "architecture", "code/code_architecture.json"
        )
        self.output_chunks = self.path_memoire / outputs.get(
            "chunks", "code/code_chunks.jsonl"
        )
        self.output_faiss = self.path_memoire / outputs.get(
            "faiss_index", "code/code_chunks.faiss"
        )
        self.output_meta = self.path_memoire / outputs.get(
            "faiss_meta", "code/code_chunks_meta.json"
        )
        self.output_skeleton = self.output_arch.parent / "scripts_skeleton.txt"

        # Création dossier si absent
        self.output_arch.parent.mkdir(parents=True, exist_ok=True)
        self.PY_EXT = ".py"

        self.logger.info("✅ MoteurVecteurCode prêt (Auditor connected).")

    def _charger_config(self) -> Dict:
        """Charge config_recherchecode.yaml via Auditor."""
        if self.path_config_dir.exists():
            file_path = self.path_config_dir / "config_recherchecode.yaml"
            if file_path.exists():
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        return yaml.safe_load(f).get("configuration", {})
                except Exception:
                    pass
        return {}  # Fallback

    def _est_exclu(self, path_obj: Path) -> bool:
        """
        Vérifie si le chemin complet contient un élément interdit.
        Analyse chaque partie du chemin (dossiers parents) et le nom du fichier.
        """
        # Liste noire stricte
        BLACKLIST = {
            "backups",
            "backup",
            "save",
            "saves",
            "old",
            "archive",
            "archives",
            "trash",
            "_trash",
            "temp",
            "tmp",
            "logs",
            "log",
            "test_output",
            ".git",
            "__pycache__",
            "venv",
            "env",
            "node_modules",
            "dist",
            "build",
            ".vscode",
            ".idea",
            "code_extraits",
            "artefacts",
        }

        # 1. Analyse des composants du chemin (dossiers)
        # ex: D:\projet\backups\mon_script.py -> parts contient "backups"
        for part in path_obj.parts:
            part_clean = part.lower()
            if part_clean in BLACKLIST:
                return True

            # Vérification partielle pour les dossiers types "backup_2025"
            if "backup" in part_clean or "archive" in part_clean:
                return True

        # 2. Vérification du nom de fichier spécifique
        nom = path_obj.name.lower()
        if any(x in nom for x in [".bak", ".tmp", ".old", "copy"]):
            return True

        return False

    # =========================================================================
    # 🧹 NETTOYAGE PRÉVENTIF
    # =========================================================================
    def _purger_artefacts(self):
        """Nettoyage avant scan."""
        targets = [
            self.output_arch,
            self.output_chunks,
            self.output_faiss,
            self.output_meta,
            self.output_skeleton,
        ]
        for f in targets:
            if f.exists():
                try:
                    f.unlink()
                except Exception:
                    pass

    # =========================================================================
    # EXECUTION PRINCIPALE
    # =========================================================================

    def run(self):
        """
        Point d'entrée du pipeline d'indexation complet.

        Exécute séquentiellement :
        1. **Purge** : Nettoyage des anciens artefacts pour éviter les conflits.
        2. **Scan & Parse** : Construction du graphe de dépendances (Architecture JSON).
        3. **Squelette** : Génération de la vue textuelle résumée pour le LLM.
        4. **Chunking** : Transformation de l'architecture en liste plate de `ContexteCode`.
        5. **Embedding** : Vectorisation et écriture de l'index FAISS (si activé).

        Cette méthode peut être longue selon la taille du projet.
        """
        self.logger.info(f"🚀 Scan avancé démarré sur : {self.root_projet}")
        self._purger_artefacts()

        # 1. Scan & Analyse Profonde
        arch = self.scanner_projet()

        # 2. Sauvegarde Architecture
        self.output_arch.write_text(
            json.dumps(arch, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # 3. Génération Vue Squelette
        try:
            skeleton_txt = self._generer_vue_squelette(arch)
            self.output_skeleton.write_text(skeleton_txt, encoding="utf-8")
        except Exception as e:
            self.logger.log_warning(f"Erreur génération squelette: {e}")

        # 4. Génération Chunks
        chunks = self.generer_chunks(arch)
        with open(self.output_chunks, "w", encoding="utf-8") as f:
            for c in chunks:
                f.write(json.dumps(asdict(c), ensure_ascii=False) + "\n")

        # 5. Vectorisation
        if self.config_data.get("vectoriel", {}).get("enabled", False):
            self.construire_index_vectoriel(chunks)

        self.logger.info("✨ Analyse terminée et index mis à jour.")

    # =========================================================================
    # 🆕 VUE SQUELETTE POUR LLM
    # =========================================================================

    def _generer_vue_squelette(self, arch: Dict[str, Any]) -> str:
        """
        Génère une représentation textuelle optimisée pour le LLM (Token-Efficient).

        Produit un "Tree View" du code qui contient l'essentiel :
        - Hiérarchie (Module -> Classe -> Méthode).
        - Signatures (pour savoir comment appeler les fonctions).
        - Docstrings (pour comprendre ce que ça fait).

        Ignore le corps des fonctions pour tenir dans la fenêtre de contexte.
        """
        lines = ["# SQUELETTE DES SCRIPTS DU SYSTÈME\n"]

        sorted_files = sorted(arch["files"].items())

        for module_name, info in sorted_files:
            path = info.get("path", "")
            # Optimisation : Ignorer les __init__ vides
            if (
                path.endswith("__init__.py")
                and not info.get("classes")
                and not info.get("functions")
            ):
                continue

            lines.append(f"📄 {module_name} ({path})")

            # Docstring du module si présent
            module_doc = info.get("module_doc", "")
            if module_doc:
                lines.append(f'  """{module_doc}"""')

            # Classes
            for cls_name, cls_info in info.get("classes", {}).items():
                bases = ", ".join(cls_info.get("bases", []))
                lines.append(f"  class {cls_name}({bases}):")

                # Docstring de la classe
                cls_doc = cls_info.get("doc", "")
                if cls_doc:
                    lines.append(f'    """{cls_doc}"""')

                # Méthodes
                for meth_name, meth_info in cls_info.get("methods", {}).items():
                    # Signature nettoyée
                    sig = meth_info.get("signature", f"def {meth_name}(...)")
                    sig = sig.replace("def ", "", 1)
                    lines.append(f"    def {sig}")

                    # Docstring de la méthode
                    meth_doc = meth_info.get("doc", "")
                    if meth_doc:
                        # Indenter le docstring pour qu'il soit sous la méthode
                        lines.append(f'      """{meth_doc}"""')

            # Fonctions Globales
            for func_name, func_info in info.get("functions", {}).items():
                sig = func_info.get("signature", f"def {func_name}(...)")
                lines.append(f"  {sig}")

                # Docstring de la fonction
                func_doc = func_info.get("doc", "")
                if func_doc:
                    lines.append(f'    """{func_doc}"""')

            lines.append("")  # Séparateur

        return "\n".join(lines)

    # =========================================================================
    # SCANNER PROJET (Identique à V1 pour l'instant)
    # =========================================================================

    def scanner_projet(self) -> Dict[str, Any]:
        """
        Orchestrateur du parcours de fichiers.

        Parcourt récursivement les dossiers configurés, applique les filtres d'exclusion
        (Blacklist), lance l'analyse AST sur chaque fichier .py valide, et construit
        la topologie des imports (Incoming/Outgoing Edges).

        Returns:
            Dict: L'objet "Architecture" complet (Graphe géant du projet).
        """
        files = {}

        include_dirs = self.config_data.get("scan", {}).get(
            "include_dirs", ["agentique"]
        )

        for dir_name in include_dirs:
            base_path = self.root_projet / dir_name
            if not base_path.exists():
                self.logger.log_warning(f"Dossier introuvable : {base_path}")
                continue

            for root, dirs, filenames in os.walk(base_path):
                # 1. Nettoyage préventif des dossiers pour os.walk
                # On retire les dossiers interdits pour ne même pas y entrer
                dirs[:] = [d for d in dirs if not self._est_exclu(Path(root) / d)]

                for filename in filenames:
                    # Construction du chemin absolu
                    full_path = Path(root) / filename

                    # 2. LE JUGE DE PAIX : Vérification sur le chemin complet
                    if self._est_exclu(full_path):
                        # print(f"🚫 Ignoré (Backup): {full_path}") # Décommentez pour debug
                        continue

                    if full_path.suffix.lower() == self.PY_EXT:
                        info = self._analyse_python_file(full_path)
                        if info:
                            files[info["module"]] = info
        # Construire incoming_edges
        for mod, info in files.items():
            incoming = set()
            for other_mod, other_info in files.items():
                if mod == other_mod:
                    continue
                for root in other_info.get("outgoing_edges", []):
                    last = mod.split(".")[-1]
                    if last == root or mod.endswith("." + root):
                        incoming.add(other_mod)
            info["incoming_edges"] = sorted(incoming)

        return {"root": str(self.root_projet), "files": files}

    # =========================================================================
    # 🆕 ANALYSE PYTHON
    # =========================================================================

    def _analyse_python_file(self, path: Path) -> Dict[str, Any]:
        """
        Cœur de l'analyse statique (AST Parser).

        Transforme un fichier texte brut en structure de données riche.
        Contrairement à une regex, l'AST permet de comprendre la portée (Scope),
        l'héritage et la structure réelle du code, même s'il est mal formaté.

        Extrait : Classes, Fonctions, Imports, Globales.
        """

        source = self._read_text(path)
        module_name = self._module_name_from_path(path)

        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            return {
                "path": str(path),
                "module": module_name,
                "error": f"SyntaxError: {e}",
                "classes": {},
                "functions": {},
                "globals": {},
                "imports": [],
                "outgoing_edges": [],
            }

        classes = {}
        functions = {}
        globals_vars = {}
        imports = []

        # 1. Extraire les imports (comme V1)
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)

        # 2. Extraire les classes avec attributs
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                # Extraire les attributs d'instance depuis __init__
                attributs_map = self._extraire_attributs_classe(node)

                methods = {}
                for sub in node.body:
                    if isinstance(sub, ast.FunctionDef):
                        methods[sub.name] = self._analyser_fonction(sub, attributs_map)

                classes[node.name] = {
                    "bases": [self._safe_name(b) for b in node.bases],
                    "methods": methods,
                    "attributes": attributs_map,
                    "doc": ast.get_docstring(node) or "",
                }

        # 3. Extraire les fonctions globales
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                functions[node.name] = self._analyser_fonction(node, {})

        # 4. Outgoing edges
        outgoing_roots = sorted(list(set(imp.split(".")[0] for imp in imports)))

        return {
            "path": str(path),
            "module": module_name,
            "classes": classes,
            "functions": functions,
            "globals": globals_vars,
            "imports": sorted(set(imports)),
            "outgoing_edges": outgoing_roots,
            "incoming_edges": [],
        }

    # =========================================================================
    # 🆕 EXTRACTION ATTRIBUTS CLASSE
    # =========================================================================

    def _extraire_attributs_classe(self, class_node: ast.ClassDef) -> Dict[str, str]:
        """
        Résolveur de dépendances intra-classe.

        Analyse le constructeur `__init__` pour identifier les composants injectés.
        Exemple : détecte que `self.agent_memoire` est de type `AgentMemoire`.

        C'est crucial pour construire le graphe d'appel : quand on voit `self.agent_memoire.sauvegarder()`,
        on sait qu'on appelle la méthode `sauvegarder` du module `AgentMemoire`.
        """
        attributs = {}

        # Chercher __init__
        for node in class_node.body:
            if isinstance(node, ast.FunctionDef) and node.name == "__init__":
                # Parser les assignations self.xxx = ...
                for stmt in ast.walk(node):
                    if isinstance(stmt, ast.Assign):
                        for target in stmt.targets:
                            if isinstance(target, ast.Attribute):
                                if (
                                    isinstance(target.value, ast.Name)
                                    and target.value.id == "self"
                                ):
                                    attr_name = target.attr

                                    # Essayer de déduire le type depuis la valeur
                                    type_deduit = self._deduire_type_depuis_valeur(
                                        stmt.value
                                    )
                                    if type_deduit:
                                        attributs[attr_name] = type_deduit

            # Annotations de classe (ex: agent_parole: AgentParole)
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name):
                    type_str = ast.unparse(node.annotation) if node.annotation else None
                    if type_str:
                        attributs[node.target.id] = type_str

        return attributs

    def _deduire_type_depuis_valeur(self, value_node: ast.AST) -> Optional[str]:
        """Déduit le type depuis une assignation (ex: AgentMemoire(...))"""

        # Cas: self.agent_memoire = AgentMemoire(...)
        if isinstance(value_node, ast.Call):
            func = value_node.func
            if isinstance(func, ast.Name):
                return func.id
            elif isinstance(func, ast.Attribute):
                return func.attr

        return None

    # =========================================================================
    # 🆕 ANALYSE FONCTION ENRICHIE
    # =========================================================================

    def _analyser_fonction(
        self, func_node: ast.FunctionDef, attributs_map: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Analyse détaillée d'une fonction ou méthode.

        Va au-delà de la simple signature en analysant le corps de la fonction pour :
        1. Identifier les appels externes (Call Graph).
        2. Résoudre les appels sur `self` grâce à `attributs_map`.
        3. Extraire le type de retour et les arguments typés.
        """

        # 1. Signature
        signature = self._extraire_signature_complete(func_node)

        # 2. Arguments et types
        args_info = {
            "args": [a.arg for a in func_node.args.args],
            "types": self._extract_types_from_args(func_node.args),
        }

        # 3. Appels de fonctions
        calls = self._analyser_appels_fonction(func_node, attributs_map)

        # 4. Type de retour
        return_type = self._extraire_type_retour(func_node)

        # 5. Variables utilisées (attributs self.xxx)
        variables_used = self._extraire_variables_utilisees(func_node)

        return {
            "signature": signature,
            "doc": ast.get_docstring(func_node) or "",
            "args": args_info["args"],
            "types": args_info["types"],
            "calls": calls,
            "return_type": return_type,
            "variables_used": variables_used,
        }

    def _extraire_signature_complete(self, func_node: ast.FunctionDef) -> str:
        """Extrait la signature complète avec annotations de types"""
        try:
            return ast.unparse(func_node).split("\n")[0]  # Première ligne seulement
        except Exception:
            # Fallback sans types
            args_str = ", ".join([a.arg for a in func_node.args.args])
            return f"def {func_node.name}({args_str})"

    def _analyser_appels_fonction(
        self, func_node: ast.FunctionDef, attributs_map: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        """
        Extrait tous les appels de fonction avec résolution.

        Ex: self.agent_parole.construire_prompt_llm(...)
          → {"module": "agent_parole", "function": "construire_prompt_llm", "line": 326}
        """
        calls = []

        for node in ast.walk(func_node):
            if isinstance(node, ast.Call):
                call_info = self._resoudre_appel(node, attributs_map)
                if call_info:
                    calls.append(call_info)

        return calls

    def _resoudre_appel(
        self, call_node: ast.Call, attributs_map: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """
        Résout un appel de fonction.

        Exemples :
        - self.agent_parole.construire_prompt_llm()
          → {"module": "AgentParole", "function": "construire_prompt_llm"}

        - moteur_llm.generer_stream()
          → {"module": "moteur_llm", "function": "generer_stream"}
        """
        func = call_node.func

        # Cas 1: self.attribut.methode()
        if isinstance(func, ast.Attribute):
            if isinstance(func.value, ast.Attribute):
                # self.agent_parole.construire_prompt_llm
                if (
                    isinstance(func.value.value, ast.Name)
                    and func.value.value.id == "self"
                ):
                    attr_name = func.value.attr  # "agent_parole"
                    method_name = func.attr  # "construire_prompt_llm"

                    # Résoudre le type depuis attributs_map
                    module_type = attributs_map.get(attr_name, attr_name)

                    return {
                        "module": module_type,
                        "function": method_name,
                        "line": call_node.lineno,
                        "resolved_from": f"self.{attr_name}",
                    }

            # Cas 2: objet.methode() (sans self)
            elif isinstance(func.value, ast.Name):
                obj_name = func.value.id
                method_name = func.attr

                return {
                    "module": obj_name,
                    "function": method_name,
                    "line": call_node.lineno,
                    "resolved_from": obj_name,
                }

        # Cas 3: Fonction simple (sans objet)
        elif isinstance(func, ast.Name):
            return {
                "module": None,
                "function": func.id,
                "line": call_node.lineno,
                "resolved_from": "global",
            }

        return None

    def _extraire_type_retour(self, func_node: ast.FunctionDef) -> Optional[str]:
        """Extrait le type de retour depuis l'annotation"""
        if func_node.returns:
            try:
                return ast.unparse(func_node.returns)
            except Exception:
                return str(func_node.returns)
        return None

    def _extraire_variables_utilisees(self, func_node: ast.FunctionDef) -> List[str]:
        """Extrait les attributs self.xxx utilisés dans la fonction"""
        variables = set()

        for node in ast.walk(func_node):
            if isinstance(node, ast.Attribute):
                if isinstance(node.value, ast.Name) and node.value.id == "self":
                    variables.add(f"self.{node.attr}")

        return sorted(list(variables))

    def _extract_types_from_args(self, args: ast.arguments) -> Dict[str, str]:
        res = {}
        all_args = list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)
        for arg in all_args:
            if arg.annotation is not None:
                try:
                    res[arg.arg] = ast.unparse(arg.annotation)
                except Exception:
                    res[arg.arg] = str(arg.annotation)
        return res

    # =========================================================================
    # 🆕 GÉNÉRATION CHUNKS ENRICHIS
    # =========================================================================

    def generer_chunks(self, arch: Dict[str, Any]) -> List[ContexteCode]:
        """
        Transformateur Architecture -> RAG.

        Convertit le graphe hiérarchique en une liste plate d'objets `ContexteCode` (Chunks).
        Chaque fonction, classe et méthode devient une entité indépendante indexable,
        enrichie de son contexte (résumé, dépendances, concepts clés).
        """
        chunks = []

        for mod, info in arch["files"].items():
            # Chunks pour les fonctions
            for f_name, f_info in info.get("functions", {}).items():
                chunks.append(
                    ContexteCode(
                        id=f"{mod}::FUNC::{f_name}",
                        type="function",
                        module=mod,
                        name=f_name,
                        signature=f_info.get("signature", f"def {f_name}(...)"),
                        docstring=f_info.get("doc", ""),
                        dependencies=f_info.get("calls", []),
                        return_type=f_info.get("return_type"),
                        variables_used=f_info.get("variables_used", []),
                        key_concepts=self._extraire_concepts(f_info.get("doc", "")),
                        code_summary=self._generer_resume_fonction(f_info),
                        score=1.0,
                    )
                )

            # Chunks pour les classes
            for c_name, c_info in info.get("classes", {}).items():
                # Chunk pour la classe elle-même
                chunks.append(
                    ContexteCode(
                        id=f"{mod}::CLASS::{c_name}",
                        type="class",
                        module=mod,
                        name=c_name,
                        signature=f"class {c_name}",
                        bases=c_info.get("bases", []),
                        attributes=c_info.get("attributes", {}),
                        methods=list(c_info.get("methods", {}).keys()),
                        docstring=c_info.get("doc", ""),
                        key_concepts=self._extraire_concepts(c_info.get("doc", "")),
                        score=1.0,
                    )
                )

                # Chunks pour chaque méthode
                for m_name, m_info in c_info.get("methods", {}).items():
                    chunks.append(
                        ContexteCode(
                            id=f"{mod}::METHOD::{c_name}.{m_name}",
                            type="method",
                            module=mod,
                            name=m_name,
                            signature=m_info.get("signature", f"def {m_name}(...)"),
                            docstring=m_info.get("doc", ""),
                            dependencies=m_info.get("calls", []),
                            return_type=m_info.get("return_type"),
                            variables_used=m_info.get("variables_used", []),
                            score=1.0,
                        )
                    )

        return chunks

    def _extraire_concepts(self, text: str) -> List[str]:
        """Extrait les concepts-clés depuis docstring/commentaires"""
        concepts = []
        text_lower = text.lower()

        keywords = {
            "orchestration",
            "streaming",
            "rag",
            "vectoriel",
            "contexte",
            "mémoire",
            "génération",
            "recherche",
            "pipeline",
            "async",
            "thread",
            "cache",
        }

        for kw in keywords:
            if kw in text_lower:
                concepts.append(kw)

        return concepts

    def _generer_resume_fonction(self, func_info: Dict) -> str:
        """Génère un résumé d'une ligne pour la fonction"""
        calls = func_info.get("calls", [])
        if calls:
            call_names = [c.get("function", "?") for c in calls[:3]]
            return f"Appelle: {', '.join(call_names)}"
        return "Fonction utilitaire"

    # =========================================================================
    # UTILITAIRES (Identiques à V1)
    # =========================================================================

    def _read_text(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return path.read_text(encoding="latin-1", errors="ignore")

    def _safe_name(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return f"{self._safe_name(node.value)}.{node.attr}"
        return ""

    def _module_name_from_path(self, py_path: Path) -> str:
        try:
            rel = py_path.relative_to(self.root_projet)
            parts = list(rel.parts)
            if parts[-1].endswith(self.PY_EXT):
                parts[-1] = parts[-1][:-3]
            return ".".join(parts)
        except ValueError:
            return py_path.stem

    def construire_index_vectoriel(self, chunks: List[ContexteCode]) -> None:
        """
        Pipeline de Vectorisation Finale.

        1. **Textification** : Crée une représentation textuelle dense de chaque chunk (Signature + Doc + Résumé).
        2. **Embedding** : Calcule les vecteurs via Sentence-BERT.
        3. **Indexation** : Stocke les vecteurs dans FAISS (Recherche rapide) et les métadonnées sur disque (Hydratation).
        """
        # Construire le texte à vectoriser depuis les ContexteCode
        texts = []
        ids = []
        for c in chunks:
            parts = [c.signature, c.docstring, c.code_summary, " ".join(c.key_concepts)]
            text = " | ".join([p for p in parts if p])
            texts.append(text)
            ids.append(c.id)

        self.logger.info(f"Construction embeddings pour {len(texts)} chunks...")
        model_name = self.config_data.get("vectoriel", {}).get(
            "model_name", "sentence-transformers/all-MiniLM-L6-v2"
        )
        model = SentenceTransformer(model_name)
        emb = model.encode(texts, convert_to_numpy=True, show_progress_bar=True)

        dim = emb.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(emb)

        faiss.write_index(index, str(self.output_faiss))

        # Sauvegarder les métadonnées + les ContexteCode sérialisés
        from dataclasses import asdict

        meta = {
            "chunks": [{"id": c.id, "data": asdict(c)} for c in chunks],
            "embedding_model": model_name,
            "version": "v2_contexte_code",
        }
        self.output_meta.write_text(
            json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        self.logger.info("✅ Index FAISS écrit avec ContexteCode")


if __name__ == "__main__":
    agent = MoteurVecteurCode()
    agent.run()
