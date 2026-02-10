#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent CodeExtractor - Détection automatique et analyse de code (Refactored & Compliant)
===========================================================================
Responsabilités :
1. Détecter et extraire le code dans les réponses du LLM (Stream).
2. Analyser statiquement des fichiers physiques (Scan).
3. Produire des métadonnées standardisées.
"""

import json
import yaml
import re
import ast
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple, Any, Optional

from agentique.base.META_agent import AgentBase

# On importe les contrats pour référence, même si on sort des dicts pour le JSON
from agentique.base.contrats_interface import ContexteCode, ArtefactCode, AnalyseContenu
from dataclasses import asdict


class CodeExtractorManager(AgentBase):
    def __init__(self, config_code: Dict = None):
        super().__init__(nom_agent="CodeExtractorManager")
        """
        Gestionnaire d'extraction de code autonome.

        Cette classe est capable de charger sa propre configuration si nécessaire (fallback) et
        d'opérer sans dépendances lourdes (pas de LLM, juste de l'AST/Regex).

        Elle standardise la sortie sous forme d'objets `ArtefactCode` enrichis d'une analyse
        syntaxique (`AnalyseContenu`), prêts à être indexés par le moteur de recherche de code.

        Attributes:
            code_dir (Path): Dossier temporaire ou définitif pour le stockage des snippets extraits.
            placeholder_tpl (str): Template du marqueur inséré dans le texte à la place du code.
        """

        # 2. Logique d'autonomie (comme AgentRecherche)
        # Si personne ne me donne de config (cas de AgentSemi), je la charge moi-même.
        if config_code is None:
            config_code = self._charger_config_disque()

        # 3. Application de la config (inchangé)
        # On gère le cas où on reçoit le fichier entier ou juste la section
        section_extraction = (
            config_code.get("extraction", {})
            if "extraction" in config_code
            else config_code
        )

        self.code_dir = Path(
            section_extraction.get("dossier_extraits", "codes_extraits")
        )
        self.placeholder_tpl = section_extraction.get(
            "placeholder_template", "<ARTIFACT_CODE ID:{id}>"
        )

        self.logger.info(f"✅ CodeExtractorManager prêt. Stockage : {self.code_dir}")

    def _charger_config_disque(self) -> Dict:
        """Méthode autonome pour lire config_code.yaml"""
        try:
            # On tente de localiser le fichier via l'Auditor ou en relatif
            path_conf = self.auditor.get_path("config")

            fichier = Path(path_conf) / "config_code.yaml"

            if fichier.exists():
                with open(fichier, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f).get("configuration", {})
            return {}
        except Exception as e:
            print(f"Erreur chargement config autonome: {e}")
            return {}

    # =========================================================================
    # 1. TRAITEMENT DU FLUX CHAT (Analyse Dynamique)
    # =========================================================================

    def traiter_reponse_llm(self, texte_original: str) -> Tuple[str, List[Dict]]:
        """
        Transformateur principal du flux de réponse.

        Parcourt le texte généré par le LLM à la recherche de blocs de code (Regex).
        Pour chaque bloc trouvé :
        1. Génère un ID unique (Hash MD5 du contenu).
        2. Lance l'analyse syntaxique profonde (_analyser_contenu_code).
        3. Crée un objet `ArtefactCode` complet.
        4. Remplace le code dans le texte par un tag <ARTIFACT_CODE ...> contenant un résumé des métadonnées.

        Args:
            texte_original (str): La réponse brute du LLM.

        Returns:
            Tuple[str, List[Dict]]:
                - Le texte nettoyé (avec placeholders).
                - La liste des artefacts extraits (sous forme de dictionnaires sérialisables).
        """
        artefacts_a_sauver = []

        def _analyse_et_remplacement(match):
            langage = match.group(1) or "python"
            code_brut = match.group(2).strip()

            if not code_brut:
                return match.group(0)

            # 1. Identification unique
            code_hash = hashlib.md5(code_brut.encode("utf-8")).hexdigest()
            id_court = code_hash[:8]

            # 2. Analyse profonde
            # Cette méthode doit maintenant retourner un objet AnalyseContenu
            obj_analyse = self._analyser_contenu_code(
                code_brut, langage, is_snippet=True
            )

            # 3. Préparation du paquet (OFFICIEL)
            artefact_obj = ArtefactCode(
                id=id_court,
                hash=code_hash,
                langage=langage,
                contenu=code_brut,
                timestamp=datetime.now().isoformat(),
                analyse=obj_analyse,  # ✅ Champ officiel
                type="snippet_llm",
            )

            # On convertit en dict pour le retour vers AgentMemoire (qui attend une liste de dicts pour le JSON)
            artefacts_a_sauver.append(asdict(artefact_obj))

            # 4. Création du placeholder
            infos = []
            if obj_analyse.classes:
                infos.append(f"{len(obj_analyse.classes)} Class")
            if obj_analyse.fonctions:
                infos.append(f"{len(obj_analyse.fonctions)} Func")

            info_str = ", ".join(infos) if infos else "Snippet"
            return f"\n<ARTIFACT_CODE ID:{id_court} LANG:{langage} INFO:[{info_str}]>\n"

        # Regex pour capturer les blocs ```langage ... ```
        pattern = r"```(\w+)?\n(.*?)```"
        texte_nettoye = re.sub(
            pattern, _analyse_et_remplacement, texte_original, flags=re.DOTALL
        )

        return texte_nettoye, artefacts_a_sauver

    # =========================================================================
    # MOTEUR D'ANALYSE (Interne)
    # =========================================================================

    def _analyser_contenu_code(
        self, content: str, langage: str, is_snippet: bool = False
    ) -> Dict:
        """
        Aiguilleur d'analyse syntaxique (Dispatcher).

        Sélectionne le parser approprié selon le langage déclaré.
        - Python -> Parser AST (Arbre syntaxique complet).
        - JS/TS -> Parser Regex robuste.
        - HTML/CSS -> Parsers spécifiques structurels.
        - JSON -> Validateur de format.
        - Autres -> Analyseur générique (comptage lignes, TODOs).

        Args:
            content (str): Le code source.
            langage (str): L'extension ou le nom du langage (ex: 'py', 'python').
            is_snippet (bool): Si True, tolère les erreurs de syntaxe (code partiel).

        Returns:
            AnalyseContenu: Objet riche contenant la structure détectée.
        """
        lang = langage.lower()
        if lang in ["python", "py"]:
            return self._analyser_python_hybride(content, is_snippet)
        elif lang in ["javascript", "js", "typescript", "ts"]:
            return self._analyser_javascript(content)
        elif lang in ["html", "htm"]:
            return self._analyser_html(content)
        elif lang == "css":
            return self._analyser_css(content)
        elif lang == "json":
            return self._analyser_json(content)
        return self._analyser_generique(content)

    def _analyser_python_hybride(
        self, content: str, is_snippet: bool
    ) -> AnalyseContenu:
        """
        Parser Python avancé (AST + Fallback Regex).

        Tente d'abord de construire l'Abstract Syntax Tree (AST) pour une précision parfaite :
        - Détection des classes (héritage, méthodes).
        - Détection des fonctions (args, async).
        - Détection des imports.

        Si l'AST échoue (ex: snippet incomplet généré par le LLM), bascule automatiquement
        sur un mode "Regex Fallback" pour extraire le maximum d'informations malgré les erreurs de syntaxe.
        """
        # 1. Initialisation des conteneurs locaux
        fonctions = []
        classes = []
        imports = []
        doc = None
        erreurs = None
        mode = "AST"

        try:
            tree = ast.parse(content)
            doc = ast.get_docstring(tree)

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    is_async = isinstance(node, ast.AsyncFunctionDef)
                    args = [a.arg for a in node.args.args]
                    # CORRECTION : On ajoute à la liste locale 'fonctions', pas à 'result["fonctions"]'
                    fonctions.append(
                        {
                            "nom": node.name,
                            "ligne": node.lineno,
                            "args": args,
                            "async": is_async,
                            "doc": ast.get_docstring(node),
                        }
                    )

                elif isinstance(node, ast.ClassDef):
                    bases = [self._get_base_name(b) for b in node.bases]
                    methods = [
                        n.name
                        for n in node.body
                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                    ]
                    # CORRECTION : On ajoute à la liste locale 'classes'
                    classes.append(
                        {
                            "nom": node.name,
                            "ligne": node.lineno,
                            "parents": bases,
                            "methodes": methods,
                            "doc": ast.get_docstring(node),
                        }
                    )

                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    if isinstance(node, ast.Import):
                        names = [n.name for n in node.names]
                    else:
                        names = [node.module] if node.module else []
                    # CORRECTION : On étend la liste locale 'imports'
                    imports.extend(names)

        except SyntaxError as e:
            mode = "REGEX_FALLBACK"
            erreurs = str(e) if not is_snippet else "Snippet incomplet"
            # Fallback Regex sur les listes locales
            fonctions = [{"nom": m} for m in re.findall(r"def\s+(\w+)", content)]
            classes = [{"nom": m} for m in re.findall(r"class\s+(\w+)", content)]
            imports = re.findall(r"(?:from|import)\s+(\w+)", content)

        # 2. Retourne l'objet officiel (Contrat Interface)
        return AnalyseContenu(
            mode=mode,
            fonctions=fonctions,
            classes=classes,
            imports=imports,
            docstring=doc,
            erreurs=erreurs,
        )

    def _get_base_name(self, node) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return f"{self._get_base_name(node.value)}.{node.attr}"
        return "Unknown"

    # --- Parsers Légers ---
    def _analyser_javascript(self, content: str) -> AnalyseContenu:
        return AnalyseContenu(
            mode="REGEX_JS",
            fonctions=[
                {"nom": m}
                for m in re.findall(
                    r"(?:function|const|let|var)\s+(\w+)\s*=?\s*(?:async\s+)?\(",
                    content,
                )
            ],
            classes=[{"nom": m} for m in re.findall(r"class\s+(\w+)", content)],
            imports=re.findall(r'import\s+.*?from\s+[\'"](.+?)[\'"]', content),
        )

    def _analyser_html(self, content: str) -> AnalyseContenu:
        tags = ["div", "span", "p", "a", "img", "script", "style", "form"]
        stats = {
            tag: len(re.findall(f"<{tag}", content, re.IGNORECASE)) for tag in tags
        }
        # HTML n'a pas de classes/fonctions au sens strict, on met tout dans extras
        return AnalyseContenu(
            mode="REGEX_HTML",
            extras={"tags_stats": {k: v for k, v in stats.items() if v > 0}},
        )

    def _analyser_css(self, content: str) -> AnalyseContenu:
        return AnalyseContenu(
            mode="REGEX_CSS",
            extras={
                "selecteurs": list(set(re.findall(r"([.#][\w-]+)\s*{", content)))[:20],
                "variables": re.findall(r"(--[\w-]+)\s*:", content)[:10],
            },
        )

    def _analyser_json(self, content: str) -> AnalyseContenu:
        valid = False
        keys = []
        try:
            data = json.loads(content)
            keys = list(data.keys()) if isinstance(data, dict) else ["Array"]
            valid = True
        except:
            pass

        return AnalyseContenu(
            mode="JSON", extras={"valid": valid, "keys_root": keys[:10]}
        )

    def _analyser_generique(self, content: str) -> AnalyseContenu:
        return AnalyseContenu(
            mode="GENERIC",
            extras={"lignes": len(content.splitlines()), "has_todo": "TODO" in content},
        )


if __name__ == "__main__":
    extractor = CodeExtractorManager()
    # Test simple
    code = "def hello(): pass"
    print(extractor.traiter_reponse_llm(f"```python\n{code}\n```"))
