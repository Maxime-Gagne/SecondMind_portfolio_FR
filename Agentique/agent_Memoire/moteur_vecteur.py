#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MoteurVectoriel - Cœur de la Mémoire Sémantique (Embeddings)
Module d'infrastructure gérant la base de données vectorielle locale du système.

Ce module encapsule la complexité mathématique de la recherche sémantique :
1.  **Vectorisation (Encoding)** : Transformation du texte en vecteurs denses via `SentenceTransformer`.
2.  **Indexation (Indexing)** : Stockage optimisé des vecteurs via `FAISS` (Facebook AI Similarity Search).
3.  **Persistance (Storage)** : Gestion synchronisée du fichier d'index binaire (.faiss) et des métadonnées JSON.

Rôle Architectural :
    Sert de backend de stockage pour :
    - La Mémoire Narrative (Souvenirs conversationnels).
    - La Mémoire Législative (Règles et Lois).
    - La Mémoire Réflexive (Traces d'erreurs passées).
"""

import os
import yaml
import json
import numpy as np
import faiss
from datetime import datetime, timezone
from dataclasses import asdict, is_dataclass
from sentence_transformers import SentenceTransformer
from agentique.base.META_agent import AgentBase
from agentique.base.contrats_interface import CustomJSONEncoder


class MoteurVectoriel(AgentBase):
    """
    Wrapper haut niveau autour de la librairie FAISS et des modèles HuggingFace.

    Cette classe gère le cycle de vie complet des données vectorielles. Elle assure
    que chaque vecteur mathématique (recherche) est strictement lié à ses métadonnées
    textuelles (résultat), garantissant l'intégrité des données retournées au RAG.

    Attributes:
        dim (int): Dimension de l'espace vectoriel (ex: 384 pour all-MiniLM-L6-v2).
        model (SentenceTransformer): Modèle d'embedding chargé en mémoire locale.
        index (faiss.Index): Structure de données optimisée pour la recherche de plus proches voisins (L2).
    """

    def __init__(self, chemin_index: str | None = None):
        super().__init__(nom_agent="MoteurVectoriel")

        # 1. Chargement Config (Source de Vérité)
        self.config = self._load_config()
        self.vec_config = self.config.get("moteur_vectoriel", {})

        # 2. Paramètres dynamiques
        self.dim = self.vec_config.get("dimension", 384)
        self.model_name = self.vec_config.get("model_name", "all-MiniLM-L6-v2")

        # 3. Chemin Index
        # Priorité : Argument > Config YAML > Auditor Default
        cfg_path_rel = self.vec_config.get("repertoire_index")
        auditor_path = self.auditor.get_path("vectorielle")

        if chemin_index:
            self.chemin_index = chemin_index
            if not os.path.exists(self.chemin_index):
                os.makedirs(self.chemin_index, exist_ok=True)
                self.logger.info(
                    f"📁 Création du dossier vectoriel dédié : {self.chemin_index}"
                )

        elif cfg_path_rel and self.auditor.get_path("memoire"):
            # Construction chemin absolu depuis racine mémoire
            self.chemin_index = os.path.join(
                self.auditor.get_path("memoire"), "..", cfg_path_rel
            )
            self.chemin_index = os.path.abspath(self.chemin_index)
        else:
            self.chemin_index = auditor_path

        self.model = SentenceTransformer(self.model_name)

        self.fichier_index = os.path.join(self.chemin_index, "index.faiss")
        self.fichier_meta = os.path.join(self.chemin_index, "metadonnees.json")

        self.index = faiss.IndexFlatL2(self.dim)
        self.metadonnees: list[dict] = []

        self._charger_index()

    def _load_config(self):
        try:
            path = self.auditor.get_path("config", "memoire")
            if not path:
                # Fallback temporaire pour instanciation hors architecture complète
                path = "config_memoire.yaml"

            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f).get("configuration", {})
        except Exception:
            pass
        return {}

        # -------------------------------
        # Sauvegarde et chargement de l'IndexVectoriel
        # -------------------------------

    def _sauvegarder_index(self):
        """
        Assure la persistance atomique du "Dual-Store".

        Sauvegarde simultanément :
        1. La structure binaire FAISS (`index.faiss`) contenant les vecteurs.
        2. Le fichier JSON (`metadonnees.json`) contenant le texte et les attributs.

        Cette synchronisation est critique : un décalage entre les deux fichiers corrompt la mémoire.
        """
        try:
            chemin_faiss = os.path.join(self.chemin_index, "index.faiss")
            chemin_meta = os.path.join(self.chemin_index, "metadonnees.json")
            os.makedirs(self.chemin_index, exist_ok=True)

            faiss.write_index(self.index, chemin_faiss)
            with open(chemin_meta, "w", encoding="utf-8") as f:
                json.dump(
                    self.metadonnees,
                    f,
                    ensure_ascii=False,
                    indent=2,
                    cls=CustomJSONEncoder,
                )
        except Exception as e:
            print(f"[ERREUR SAUVEGARDE INDEX] {e}")

    def _charger_index(self):
        """Recharge l'index FAISS et les métadonnées si disponibles."""
        try:
            chemin_faiss = os.path.join(self.chemin_index, "index.faiss")
            chemin_meta = os.path.join(self.chemin_index, "metadonnees.json")

            if os.path.exists(chemin_faiss) and os.path.exists(chemin_meta):
                self.index = faiss.read_index(chemin_faiss)
                with open(chemin_meta, "r", encoding="utf-8") as f:
                    self.metadonnees = json.load(f)
                print(
                    f"[INFO] Index vectoriel chargé ({len(self.metadonnees)} entrées)."
                )
            else:
                print("[INFO] Aucun index existant, création d'un nouveau.")
        except Exception as e:
            print(f"[ERREUR CHARGEMENT INDEX VECTORIEL] {e}")

    # -------------------------------
    # Ajout et recherche
    # -------------------------------
    def ajouter_fragment(self, texte: str, meta: dict | None = None) -> None:
        """
        Pipeline d'ingestion : Texte -> Vecteur -> Stockage.

        Processus :
        1. **Embedding** : Calcule le vecteur du texte via le modèle Transformer.
        2. **Indexation** : Ajoute le vecteur à l'index FAISS.
        3. **Enrichissement** : Injecte le contenu textuel brut dans les métadonnées (Critical Path)
           pour s'assurer que le résultat de recherche contient la donnée lisible, pas juste un ID.
        4. **Commit** : Déclenche une sauvegarde immédiate sur disque.

        Args:
            texte (str): Le contenu brut à vectoriser.
            meta (dict, optional): Métadonnées contextuelles (Timestamp, Source, Type).
        """
        if not texte or not texte.strip():
            return

        # ✅ Conversion Dataclass -> Dict si nécessaire
        if is_dataclass(meta):
            meta = asdict(meta)

        meta = dict(meta or {})
        meta.setdefault("timestamp", datetime.now(timezone.utc).isoformat())

        # CORRECTION CRITIQUE : Sauvegarde du contenu textuel
        # Sans cela, la recherche renvoie un emplacement vide.
        if "contenu" not in meta:
            meta["contenu"] = texte

        v = self.model.encode([texte])[0].astype(np.float32)
        self.index.add(np.array([v]))

        meta.setdefault("len", len(texte))
        self.metadonnees.append(meta)
        self._sauvegarder_index()

    def rechercher(self, requete: str, top_k: int = 5) -> list[dict]:
        """
        Exécute une recherche par similarité sémantique (Semantic Search).

        Processus :
        1. Vectorise la requête utilisateur (Query Embedding).
        2. Interroge FAISS pour trouver les `top_k` plus proches voisins (Distance L2).
        3. Convertit la distance euclidienne en score de similarité normalisé (0 à 1).
        4. Reconstruit les objets résultats en fusionnant score et métadonnées.

        Args:
            requete (str): La phrase ou le concept à rechercher.
            top_k (int): Nombre de résultats maximum à retourner.

        Returns:
            list[dict]: Liste de résultats formatés [{"score": float, "meta": dict}].
        """
        if self.index.ntotal == 0:
            return []
        vq = self.model.encode([requete])[0].astype(np.float32)
        D, I = self.index.search(np.array([vq]), top_k)
        out = []
        for idx, dist in zip(I[0], D[0]):
            if 0 <= idx < len(self.metadonnees):
                out.append(
                    {"score": 1.0 / (1.0 + float(dist)), "meta": self.metadonnees[idx]}
                )
        return out
