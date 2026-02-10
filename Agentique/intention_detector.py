#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import torch
import yaml

from pathlib import Path
from typing import List, Optional, Dict
from sentence_transformers import SentenceTransformer
from agentique.base.META_agent import AgentBase
from agentique.base.contrats_interface import (
    Sujet,
    Action,
    Categorie,
    ResultatIntention,
)


# ============================================================
#  UTILITAIRE : CHARGEMENT CLASSIFIEUR
# ============================================================
class ClassifierHead(torch.nn.Module):
    """
    Classe PyTorch qui doit matcher exactement le modèle du script d'entraînement.
    (SBERT -> Embedding -> MLP 256 -> nb_labels)
    """

    def __init__(self, emb_dim: int, nb_labels: int):
        super().__init__()
        self.net = torch.nn.Sequential(
            torch.nn.Linear(emb_dim, 256),
            torch.nn.ReLU(),
            torch.nn.Linear(256, nb_labels),
        )

    def forward(self, x):
        return self.net(x)


# ============================================================
#  AGENT PRINCIPAL
# ============================================================
class IntentionDetector(AgentBase):
    """
    IntentionDetector v4 — SBERT + 3 classifieurs PyTorch
    Piloté EXCLUSIVEMENT par le YAML.
    Zéro hardcode.
    """

    def __init__(self):
        super().__init__(nom_agent="IntentionDetector")

        # ------------------------------------------------------------
        # 1) Charger config YAML
        # ------------------------------------------------------------
        chemin_config_mini_llm = self.auditor.get_path("config", nom_agent="minillm")
        
        if not chemin_config_mini_llm:
            self.logger.log_error("❌ Chemin de configuration MINI_LLM introuvable via Auditor.")
            raise RuntimeError("Configuration absente.")
        
        try:
            with open(chemin_config_mini_llm, "r", encoding="utf-8") as f:
                self.cfg = yaml.safe_load(f)
        except Exception as e:
            raise RuntimeError(f"Impossible de lire YAML {chemin_config_mini_llm}: {e}")

        self.cfg_sbert = self.cfg["models"]["SbertClassifier"]

        # MODEL PATHS
        self.sbert_path = self.cfg_sbert["base_model_path"]
        self.label_map_path = self.cfg_sbert["label_map_path"]

        # PATHS classifieurs (un par axe)
        base_dir = Path(self.cfg_sbert["classifier_head_path"]).parent
        self.path_classifier_sujet = base_dir / "classifier_sujet.pth"
        self.path_classifier_action = base_dir / "classifier_action.pth"
        self.path_classifier_categorie = base_dir / "classifier_categorie.pth"

        self.device = self.cfg_sbert["loading"].get("device", "cuda")

        self.logger.info(f"⚙️ Initialisation IntentionDetector SBERTClassifier | device={self.device}")

        # ------------------------------------------------------------
        # 2) Charger SBERT
        # ------------------------------------------------------------
        try:
            self.sbert = SentenceTransformer(self.sbert_path, device=self.device)
        except Exception as e:
            raise RuntimeError(f"Échec chargement SBERT ({self.sbert_path}): {e}")

        self.emb_dim = self.sbert.get_sentence_embedding_dimension()
        self.logger.info(f"✅ SBERT chargé ({self.sbert_path}) | Embedding dim = {self.emb_dim}")

        # ------------------------------------------------------------
        # 3) Charger label_map.json (ta taxonomie)
        # ------------------------------------------------------------
        try:
            with open(self.label_map_path, "r", encoding="utf-8") as f:
                self.label_map: Dict[str, Dict[str, str]] = json.load(f)
        except Exception as e:
            raise RuntimeError(f"Impossible de lire label_map JSON ({self.label_map_path}): {e}")

        # ------------------------------------------------------------
        # 4) Construire espaces de labels
        # ------------------------------------------------------------
        self.labels_sujet = list(self.label_map["Sujet"].values())
        self.labels_action = list(self.label_map["Action"].values())
        self.labels_categorie = list(self.label_map["Categorie"].values())

        # index -> label (inverse mapping)
        self.id2sujet = {i: lbl for i, lbl in enumerate(self.labels_sujet)}
        self.id2action = {i: lbl for i, lbl in enumerate(self.labels_action)}
        self.id2categorie = {i: lbl for i, lbl in enumerate(self.labels_categorie)}

        # ------------------------------------------------------------
        # 5) Charger les classifieurs PyTorch
        # ------------------------------------------------------------
        self.classifier_sujet = ClassifierHead(self.emb_dim, len(self.labels_sujet)).to(self.device)
        self.classifier_action = ClassifierHead(self.emb_dim, len(self.labels_action)).to(self.device)
        self.classifier_categorie = ClassifierHead(self.emb_dim, len(self.labels_categorie)).to(self.device)

        self._load_classifier_weights()

        self.logger.info("✅ IntentionDetector_SBERTClassifier initialisé.")

    # ------------------------------------------------------------
    # Charger les poids PyTorch
    # ------------------------------------------------------------
    def _load_classifier_weights(self):
        def load(pth: Path, model: torch.nn.Module, axis: str):
            if not pth.exists():
                raise RuntimeError(
                    f"❌ Classifier {axis} introuvable : {pth}\n"
                    f"→ As-tu bien exécuté entrainement_intention_sbert.py ?"
                )
            try:
                model.load_state_dict(torch.load(pth, map_location=self.device))
                model.eval()
                self.logger.info(f"🔹 Classifieur {axis} chargé → {pth.name}")
            except Exception as e:
                raise RuntimeError(f"Erreur chargement classifieur {axis}: {e}")

        load(self.path_classifier_sujet, self.classifier_sujet, "Sujet")
        load(self.path_classifier_action, self.classifier_action, "Action")
        load(self.path_classifier_categorie, self.classifier_categorie, "Categorie")

    # ------------------------------------------------------------
    # Construction contexte
    # ------------------------------------------------------------
    def _construire_contexte(self, prompt: str, historique: Optional[List[str]]):
        if not historique:
            return prompt

        morceaux = []
        try:
            start = max(0, len(historique) - 4)
            for i in range(start, len(historique), 2):
                u = historique[i]
                a = historique[i + 1] if i + 1 < len(historique) else ""
                morceaux.append(f"U: {u}")
                if a:
                    morceaux.append(f"A: {a}")
        except:
            return prompt

        morceaux.append(f"U: {prompt}")
        return "\n".join(morceaux)

    # ------------------------------------------------------------
    # API PRINCIPALE
    # ------------------------------------------------------------
    def intention_detector(
        self,
        prompt: str,
        historique_brut: Optional[List[str]] = None
    ) -> ResultatIntention:

        self.logger.log_thought(f"[SBERTClassifier] Prompt: {prompt[:80]!r}")

        # 1) Encoder
        texte = self._construire_contexte(prompt, historique_brut)
        emb = self.sbert.encode(texte, normalize_embeddings=True, convert_to_tensor=True)
        emb = emb.to(self.device).float()

        # 2) Passer dans les 3 classifieurs
        with torch.no_grad():
            id_sujet = self.classifier_sujet(emb).argmax().item()
            id_action = self.classifier_action(emb).argmax().item()
            id_categorie = self.classifier_categorie(emb).argmax().item()

        # 3) Convertir → valeurs finales
        sujet_val = self.id2sujet[id_sujet]
        action_val = self.id2action[id_action]
        categorie_val = self.id2categorie[id_categorie]

        self.logger.info(
            f"🎯 SBERTClassifier → {sujet_val} / {action_val} / {categorie_val}"
        )

        # 4) Convertir → enums
        sujet_enum = Sujet(sujet_val)
        action_enum = Action(action_val)
        categorie_enum = Categorie(categorie_val)

        resultat = ResultatIntention(
        prompt=prompt,
        sujet=sujet_enum,
        action=action_enum,
        categorie=categorie_enum
    )
        # ✅ Validation du contrat de sortie (Sécurité Runtime)
        self.auditor.valider_format_sortie(resultat)
        
        return resultat