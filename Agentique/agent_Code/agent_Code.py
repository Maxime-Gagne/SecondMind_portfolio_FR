#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent Code - Orchestrateur de l'Intelligence Code
=================================================
Responsabilité : Cerveau central du code.
1. Possède les outils (MoteurVecteurCode, CodeExtractorManager).
2. Gère la Lecture (RAG Hybride : Vecteurs + Graphe).
3. Gère l'Écriture (Déclenche l'indexation).
4.Gère l'outil de recherche de documentation externe.

Rôle Architectural :
    Agit comme le "CTO virtuel" du système. Il fournit à l'AgentSemi le contexte technique précis
    nécessaire pour générer du code valide, respectant les interfaces existantes et les imports.
"""

import json
import yaml
from pathlib import Path
from typing import List, Dict, Optional, Any
import faiss
import requests
from sentence_transformers import SentenceTransformer
from dataclasses import asdict

# Imports des Outils Renommés
from .code_extractor_manager import CodeExtractorManager
from .outils.moteur_vecteur_code import MoteurVecteurCode
from agentique.base.contrats_interface import ContexteCode, Souvenir
from agentique.base.META_agent import AgentBase


class AgentCode(AgentBase):
    def __init__(self):
        super().__init__(nom_agent="AgentCode")
        """
        Expert technique et gardien de la cohérence du code.

        Cette classe centralise l'accès aux outils d'analyse statique et dynamique.
        Elle gère le chargement en RAM des index lourds (Architecture, Embeddings) pour garantir
        une latence minimale lors des requêtes de contexte "Hot Path".

        Attributes:
            moteur_vecteur (MoteurVecteurCode): Outil d'indexation et de recherche vectorielle.
            extractor_manager (CodeExtractorManager): Gestionnaire de parsing AST pour l'extraction de métadonnées.
            arch (Dict): Graphe de dépendances chargé en mémoire.
        """
        self.config = self._charger_config()

        # 1. Initialisation des Outils avec leur section de config dédiée
        self.moteur_vecteur = MoteurVecteurCode()
        # On passe la section 'extraction' au manager
        self.extractor_manager = CodeExtractorManager(self.config.get("extraction", {}))
        # Utilisation des URLs du YAML pour la doc externe
        self.doc_cfg = self.config.get("documentation_externe", {})

        # 2. Configuration & Chemins
        self.config = self._charger_config()
        path_memoire = Path(self.auditor.get_path("memoire"))
        outputs = self.config.get("output_paths", {})

        self.arch_path = path_memoire / outputs.get(
            "architecture", "code/code_architecture.json"
        )
        self.chunks_jsonl = path_memoire / outputs.get(
            "chunks", "code/code_chunks.jsonl"
        )
        self.faiss_index_path = path_memoire / outputs.get(
            "faiss_index", "code/code_chunks.faiss"
        )
        self.faiss_meta_path = path_memoire / outputs.get(
            "faiss_meta", "code/code_chunks_meta.json"
        )

        # 3. Chargement de l'Index en RAM (Lecture)
        self.arch = {}
        self.chunk_offsets = {}
        self.index = None
        self.meta = {}
        self.embedder = None

        self._charger_index_en_memoire()

        self.logger.info("✅ AgentCode prêt (Cerveau + Outils connectés).")

    # ============================================================
    # 1. API PUBLIQUE (Appelée par Semi)
    # ============================================================

    def fournir_contexte(self, question: str, top_k: int = 8) -> List[Any]:
        """
        API Principale : Transforme une question technique en un contexte code riche.

        Orchestre le pipeline de récupération :
        1. **Recherche Hybride** : Combine les résultats vectoriels (concepts) et symboliques (noms de modules).
        2. **Squelette Dynamique** : Génère une "Map" allégée ne contenant que l'arborescence des modules pertinents.
        3. **Documentation Externe** : Si des librairies critiques (ex: Pydantic) sont détectées, interroge le serveur de doc.
        4. **Validation** : Vérifie et formate chaque artefact (ContexteCode) avant retour.

        Args:
            question (str): La demande technique de l'utilisateur.
            top_k (int): Nombre de snippets de code à récupérer.

        Returns:
            List[Any]: Liste hétérogène d'objets (Souvenir, ContexteCode) prêts pour l'injection.
        """
        contexte_final = []
        try:
            # 1. Recherche Hybride (Logique interne)
            resultats = self.chercher_code(question, top_k)
            modules_concernes = resultats.get("modules_concernes", [])
            objets_code = resultats.get("contexte_objets", [])

            if not modules_concernes and not objets_code:
                raise ValueError(
                    f"❌ fournir_contexte: Aucun code trouvé pour '{question}' - Index vide ou question hors scope?"
                )

            # 2. GÉNÉRATION DU SQUELETTE DYNAMIQUE
            # On demande au moteur de filtrer le squelette complet pour ces modules
            squelette_pertinent = self._generer_squelette_partiel(modules_concernes)

            if squelette_pertinent:
                contexte_final.append(
                    Souvenir(
                        contenu=squelette_pertinent,
                        titre="SQUELETTE_DYNAMIQUE_PERTINENT",
                        type="code_structure",
                        score=10.0,
                    )
                )

            if objets_code:
                contexte_final.extend(objets_code)
                self.logger.info(
                    f"💻 Contexte Code : {len(modules_concernes)} modules, {len(objets_code)} chunks."
                )

            # --- AJOUT : Recherche Documentation Externe ---
            libs_critiques = [
                "pydantic",
                "trl",
                "peft",
                "transformers",
                "langchain",
                "fastapi",
            ]
            if any(lib in question.lower() for lib in libs_critiques):
                doc_externe = self.consulter_documentation_externe(question)

                if doc_externe:
                    # ❌ SUPPRIMER CETTE LIGNE (Ligne 79 dans ton fichier) :
                    # from agentique.base.contrats_interface import Souvenir

                    # On utilise directement la classe globale
                    contexte_final.append(
                        Souvenir(
                            contenu=doc_externe,
                            titre="DOCUMENTATION_TECHNIQUE_OFFICIELLE",
                            type="documentation_externe",
                            score=10.0,
                        )
                    )
                    self.logger.info(f"📚 Doc externe injectée pour : {question}")

            # 🛡️👁️‍🗨️🛡️# VALIDATION FORMAT SORTIE
            # On valide chaque item (qui peut être Souvenir ou ContexteCode)
            for item in contexte_final:
                self.auditor.valider_format_sortie(item)

            return contexte_final

        except Exception as e:
            self.logger.log_error(f"Erreur contexte code: {e}")
            # On retourne un objet ContexteCode valide, mais qui crie l'erreur.
            # Cela permet à Semi de continuer sans masquer le problème.
            from agentique.base.contrats_interface import ContexteCode

            erreur_artefact = ContexteCode(
                id="ERROR_CRITICAL",
                type="erreur_technique",  # Type spécial détecté par Semi
                module="AgentCode",
                name="EXCEPTION_RUNTIME",
                contenu=f"⚠️ ÉCHEC CRITIQUE RÉCUPÉRATION CODE : {str(e)}.\n"
                f"Le contexte technique est indisponible pour cette requête.",
                score=1.0,  # Score max pour être sûr d'être inclus dans le contexte
            )
            return [erreur_artefact]

    # -------------------------------------------------------------------------
    # NOUVELLE MÉTHODE : Filtrage intelligent du Squelette via Graphe
    # -------------------------------------------------------------------------
    def _generer_squelette_partiel(self, modules_cibles: List[str]) -> str:
        """
        Générateur de "Carte Topologique" ciblée.

        Au lieu de dumper l'architecture complète du projet (trop verbeuse pour le LLM),
        cette méthode construit une vue filtrée ne montrant que la structure (Classes/Méthodes)
        des modules identifiés comme pertinents.

        Permet au LLM de "voir" où il doit intervenir sans polluer sa fenêtre de contexte.

        Args:
            modules_cibles (List[str]): Liste des noms de modules (ex: 'agent_Code.py').

        Returns:
            str: Représentation arborescente textuelle (Tree view).
        """
        if not self.arch or not modules_cibles:
            return ""

        lines = ["# SQUELETTE DYNAMIQUE (Ciblé sur votre demande)\n"]

        # On trie pour l'affichage propre
        for mod_name in sorted(modules_cibles):
            # ✅ CORRECTION : Utilisation de self.arch["files"]
            info = self.arch.get("files", {}).get(mod_name)
            if not info:
                continue

            path = info.get("path", mod_name)
            lines.append(f"📦 MODULE : {mod_name} ({path})")

            # On affiche les classes et méthodes (Signatures uniquement)
            for cls_name, cls_info in info.get("classes", {}).items():
                lines.append(f"  └── class {cls_name}")
                for meth in cls_info.get("methods", {}):
                    lines.append(f"      └── def {meth}")

            for func_name in info.get("functions", {}):
                lines.append(f"  └── def {func_name}")

            lines.append("")  # Espace

        return "\n".join(lines)

    def rafraichir_index(self) -> bool:
        """
        Déclenche la ré-indexation complète du code (Hot Reload).

        Appelé après une modification de fichier pour garantir que la mémoire de l'agent
        est synchronisée avec la réalité du disque.
        1. Lance le worker d'indexation (MoteurVecteurCode).
        2. Recharge les structures de données en RAM (Architecture, FAISS).
        """
        self.logger.info("🔄 AgentCode : Rafraîchissement index demandé...")
        try:
            # 1. Lancer le worker lourd (Scan Disque -> JSONL/FAISS)
            self.moteur_vecteur.run()

            # 2. Recharger la RAM (Hot Reload)
            self._charger_index_en_memoire()

            self.logger.info("✅ AgentCode : Index mis à jour et rechargé.")
            return True
        except Exception as e:
            self.logger.log_error(f"❌ Erreur rafraîchissement index: {e}")
            return False

    # ============================================================
    # 2. LOGIQUE MOTEUR LECTURE (Interne)
    # ============================================================

    def chercher_code(self, question: str, top_k: int = 8) -> Dict:
        """
        Cœur algorithmique du RAG Hybride.

        Combine trois stratégies de recherche :
        A. **Vectorielle** : Trouve les snippets sémantiquement proches (ex: "gestion mémoire" -> agent_Memoire.py).
        B. **Symbolique** : Trouve les modules par mots-clés exacts dans le nom ou le chemin.
        C. **Expansion de Graphe** : Utilise le graphe de dépendances pour inclure les modules liés (Imports directs).

        Returns:
            Dict: Contient les modules identifiés (pour le squelette) et les objets code (pour le contexte).
        """
        # A. Recherche Vectorielle (Retourne des ContexteCode)
        vect_chunks_objs = self._search_vector(question, top_k=top_k)

        # B. Recherche Symbolique (Retourne des dicts simples)
        symb_modules = self._trouver_modules_par_mots_cles(question)

        # C. Fusion & Expansion Graphe
        modules_vect = [c.module for c in vect_chunks_objs if c.module]
        modules_symb = [m["nom"] for m in symb_modules]

        all_modules = set(modules_symb + modules_vect)
        expanded_modules = self._expand_dependencies(list(all_modules), depth=1)

        return {
            "modules_concernes": expanded_modules,
            "contexte_objets": vect_chunks_objs,
        }

    # --- Utilitaires de Chargement ---

    def _charger_config(self) -> Dict:
        path_config = self.auditor.get_path("config")
        if path_config:
            file_path = Path(path_config) / "config_recherche_code.yaml"
            if file_path.exists():
                with open(file_path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f).get("configuration", {})
        return {}

    def _charger_index_en_memoire(self):
        """Charge Architecture + Offsets + FAISS"""
        # Architecture
        if self.arch_path.exists():
            with open(self.arch_path, "r", encoding="utf-8") as f:
                self.arch = json.load(f)

        # Offsets JSONL (Optimisation RAM)
        if self.chunks_jsonl.exists():
            self.chunk_offsets = {}
            with open(self.chunks_jsonl, "rb") as f:
                while True:
                    offset = f.tell()
                    line = f.readline()
                    if not line:
                        break
                    try:
                        c_id = json.loads(line.decode("utf-8")).get("id")
                        if c_id:
                            self.chunk_offsets[c_id] = offset
                    except:
                        continue

        # FAISS
        if self.faiss_index_path.exists():
            self.index = faiss.read_index(str(self.faiss_index_path))
            with open(self.faiss_meta_path, "r", encoding="utf-8") as f:
                self.meta = json.load(f)

            model_name = self.config.get("vectoriel", {}).get(
                "model_name", "sentence-transformers/all-MiniLM-L6-v2"
            )
            self.embedder = SentenceTransformer(model_name)

    # --- Utilitaires de Recherche (Vecteur / Graphe) ---

    def _search_vector(self, query, top_k=5) -> List[ContexteCode]:
        """
        Exécute la recherche FAISS et hydrate les résultats.

        Fait le lien entre l'index vectoriel (qui ne contient que des IDs) et
        le fichier JSONL (qui contient les données riches).
        Transforme les JSON bruts en objets `ContexteCode` typés et validés.
        """
        if self.index is None:
            raise RuntimeError("❌ _search_vector: Index FAISS non chargé!")
        if self.embedder is None:
            raise RuntimeError("❌ _search_vector: Embedder non initialisé!")
        if not self.meta:
            raise RuntimeError("❌ _search_vector: Métadonnées FAISS vides!")

        query_emb = self.embedder.encode([query])
        scores, indices = self.index.search(query_emb, top_k)

        results_objs = []
        meta_chunks = self.meta.get("chunks", [])

        # On utilise zip pour avoir score et index
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(meta_chunks):
                continue

            chunk_id = meta_chunks[idx].get("id")
            offset = self.chunk_offsets.get(chunk_id)

            if offset is not None:
                try:
                    with open(self.chunks_jsonl, "rb") as f:
                        f.seek(offset)
                        line = f.readline()
                        if line:
                            d = json.loads(line.decode("utf-8"))

                            # ✅ HYDRATATION VERS DATACLASS ContexteCode
                            # On mappe les champs JSON vers la Dataclass stricte
                            c_obj = ContexteCode(
                                id=d.get("id", "unknown"),
                                type=d.get("type", "snippet"),
                                module=d.get("module", "unknown"),
                                name=d.get("name", "unknown"),
                                signature=d.get("signature", ""),
                                docstring=d.get("docstring", ""),
                                dependencies=d.get("dependencies", []),
                                key_concepts=d.get("key_concepts", []),
                                code_summary=d.get("code_summary", ""),
                                contenu=d.get("contenu", ""),
                                score=float(score),  # On injecte le score FAISS
                                return_type=d.get("return_type"),
                                variables_used=d.get("variables_used", []),
                                bases=d.get("bases", []),
                                attributes=d.get("attributes", {}),
                                methods=d.get("methods", []),
                            )
                            results_objs.append(c_obj)
                except Exception as e:
                    print(f"[Erreur lecture/hydratation chunk] {chunk_id}: {e}")
                    continue

        return results_objs

    def _trouver_modules_par_mots_cles(self, phrase_query):
        """
        Découpe la phrase en mots pour trouver les modules correspondants.
        """
        resultats = []
        fichiers = self.arch.get("files", {})

        # 1. Découpage intelligent (On garde les mots significatifs > 3 chars)
        mots_cles = [m.strip() for m in phrase_query.split() if len(m.strip()) > 3]

        if not mots_cles:
            return []

        for nom, info in fichiers.items():
            docstring = info.get("docstring", "") or ""
            path = info.get("path", "")

            # 2. Matching sur n'importe quel mot clé
            # Ex: "agent_Parole" dans "agent_Parole.py" -> MATCH
            if any(k in nom or k in path for k in mots_cles):
                resultats.append(
                    {"nom": nom, "path": path, "resume": docstring[:100] + "..."}
                )
        return resultats

    def _expand_dependencies(self, modules: List[str], depth: int = 1) -> List[str]:
        if not self.arch:
            return modules
        full = set(modules)
        for _ in range(depth):
            new = set()
            for mod in list(full):
                info = self.arch.get("files", {}).get(mod, {})
                for dep in info.get("outgoing_edges", []):
                    for m in self.arch.get("files", {}):  # ✅ Correction accès
                        if m == dep or m.endswith("." + dep):
                            new.add(m)
            full.update(new)
        return list(full)

    def consulter_documentation_externe(self, query: str, k: int = 3) -> str:
        """
        Interface avec le Serveur de Documentation (Micro-service Python).

        Permet à l'agent d'accéder à la documentation "fraîche" de librairies tierces,
        contournant la date de coupure de connaissance du LLM (Knowledge Cutoff).
        Gère les timeouts pour ne pas bloquer le processus de réflexion principal.

        Args:
            query (str): Nom de la librairie ou concept à documenter.
        """
        try:
            url = "http://localhost:5000/api/search"
            payload = {"query": query, "k": k}

            # Timeout court pour ne pas bloquer la pensée si le serveur doc est éteint
            response = requests.post(url, json=payload, timeout=2.0)

            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])

                if not results:
                    return ""

                # Formatage pour le contexte du LLM
                contexte_doc = "\n### 📚 DOCUMENTATION OFFICIELLE (SCRAPÉE & À JOUR)\n"
                for res in results:
                    pkg = res.get("package", "Inconnu")
                    content = res.get("content", "").strip()
                    score = res.get("score", 0.0)
                    contexte_doc += f"--- {pkg} (Score: {score:.2f}) ---\n{content}\n\n"

                return contexte_doc

        except requests.exceptions.ConnectionError:
            self.logger.log_warning(
                "⚠️ Doc Server (Port 5000) injoignable. On continue sans doc externe."
            )
        except Exception as e:
            self.logger.log_error(f"Erreur interrogation Doc Server: {e}")

        return ""
