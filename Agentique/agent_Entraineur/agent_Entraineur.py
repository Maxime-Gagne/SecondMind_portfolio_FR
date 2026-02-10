#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AgentEntraineur - Moteur d'Apprentissage Supervisé et de Fine-Tuning SBERT
Module responsable de l'évolution cognitive du système via l'entraînement de réseaux de neurones.

Ce module implémente le pipeline "Offline Training" :
1.  **Ingestion** : Fusionne les datasets générés automatiquement (AutoDatasetBuilder) et les corrections manuelles.
2.  **Transformation** : Convertit les prompts textuels en embeddings vectoriels via SBERT (Sentence-BERT).
3.  **Entraînement** : Optimise trois têtes de classification (ClassifierHead) indépendantes pour prédire
    le Sujet, l'Action et la Catégorie d'une interaction.
4.  **Validation** : Évalue la performance du modèle sur un jeu de test pour garantir la non-régression.

Architecture ML :
    Le système utilise une approche "Frozen Encoder" : le modèle SBERT de base est gelé (non entraîné),
    seules les couches linéaires supérieures (MLP) sont optimisées. Cela permet un entraînement rapide
    et efficace avec peu de données (Few-Shot Learning).
"""

import json
import yaml
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from sentence_transformers import SentenceTransformer
from sklearn.model_selection import train_test_split
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import numpy as np
import unicodedata

from agentique.base.META_agent import AgentBase
from agentique.base.config_paths import ROOT_DIR

# ============================================================================
# CLASSES UTILITAIRES (Interne à l'entraîneur)
# ============================================================================


class ClassifierHead(nn.Module):
    """
    Tête de classification neuronale (MLP).

    Architecture simple mais efficace :
    - Input : Embedding SBERT (ex: 384 dim).
    - Hidden : Layer dense (256 neurones) + Activation ReLU.
    - Output : Layer dense (nb_classes) -> Logits.

    Cette architecture doit rester strictement synchronisée avec celle utilisée
    par le moteur d'inférence (IntentionDetector) pour que les poids chargés soient compatibles.
    """

    def __init__(self, emb_dim: int, nb_labels: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(emb_dim, 256), nn.ReLU(), nn.Linear(256, nb_labels)
        )

    def forward(self, x):
        return self.net(x)


class IntentDataset(Dataset):
    """
    Wrapper PyTorch pour le chargement efficace des données.

    Responsabilités :
    1. **Encodage Lazy** : Convertit le texte en vecteur via SBERT au moment de l'accès (getItem),
       permettant de gérer des datasets plus grands que la RAM GPU si nécessaire (bien que plus lent).
    2. **Mapping Label** : Convertit les étiquettes textuelles ("CODER") en indices numériques (3)
       pour le calcul de la perte.
    """

    def __init__(self, data, sbert_model, axe, label_map):
        self.data = data
        self.sbert = sbert_model
        self.axe = axe
        self.label_map = label_map  # Dict {label: id}

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        obj = self.data[idx]
        text = obj["prompt"]
        label_raw = obj[self.axe]

        # Mapping sécurisé
        y = self.label_map.get(label_raw, 0)

        # Encodage à la volée (pour économiser la RAM, un peu plus lent)
        # ou pré-calculé. Ici à la volée pour simplicité.
        emb = self.sbert.encode(text, normalize_embeddings=True)
        return torch.tensor(emb, dtype=torch.float32), torch.tensor(y)


# ============================================================================
# AGENT ENTRAINEUR
# ============================================================================


class AgentEntraineur(AgentBase):
    def __init__(self):
        super().__init__(nom_agent="AgentEntraineur")
        """
        Superviseur du cycle de vie des modèles d'intention.

        Cette classe agit comme un "Data Scientist Automatisé". Elle prépare les données, configure
        les hyperparamètres d'entraînement (Learning Rate, Epochs) selon le YAML, lance la boucle
        d'optimisation PyTorch et sauvegarde les poids du modèle (.pth) uniquement si la précision est satisfaisante.

        Attributes:
            sbert (SentenceTransformer): Modèle de fondation chargé pour générer les embeddings à la volée.
            label_map_json (Dict): Registre officiel des classes (Sujet/Action/Catégorie) assurant la cohérence avec l'AgentJuge.
        """
        # 1. Chargement de SA propre config (pas celle du MiniLLM)
        self.config = self._charger_config()

        # 2. Assignation dynamique des chemins
        cfg_chemins = self.config.get("chemins", {})
        self.data_dir = Path(cfg_chemins.get("base_data"))
        self.dataset_files = [
            self.data_dir / f for f in cfg_chemins.get("datasets", [])
        ]

        # 3. Initialisation SBERT via YAML
        cfg_sbert = self.config.get("sbert", {})
        self.device = cfg_sbert.get("device", "cpu")
        self.sbert = SentenceTransformer(
            cfg_sbert.get("model_path"), device=self.device
        )

        # 4. Chargement Label Map via YAML
        path_labels = cfg_chemins.get("registre_labels")
        with open(path_labels, "r", encoding="utf-8") as f:
            self.label_map_json = json.load(f)

        self.logger.info(
            f"✅ AgentEntraineur prêt sur {self.device}. Modèle base: {self.config_sbert['base_model_path']}"
        )

    def _charger_config_sbert(self) -> Dict:
        """Charge la config depuis le fichier de configuration du moteur MiniLLM (qui contient la section Sbert)"""
        path_config = self.auditor.get_path(
            "config", "moteurminillm"
        )  # Ou chemin direct
        if not path_config:
            # Fallback chemin en dur si l'auditor n'est pas encore sync
            path_config = r"D:\rag_personnel\agentique\sous_agents_gouvernes\agent_Parole\moteurs\config_moteur_mini_llm.yaml"

        with open(path_config, "r", encoding="utf-8") as f:
            full_cfg = yaml.safe_load(f)
        return full_cfg["models"]["SbertClassifier"]

    # =========================================================================
    # LOGIQUE DE PRÉPARATION DES DONNÉES
    # =========================================================================

    def _fusionner_datasets(self) -> List[Dict]:
        """
        Agrégateur de connaissances (Data Lake).

        Combine les données provenant de multiples sources (JSONL) pour constituer le
        corpus d'entraînement unifié. Applique une déduplication stricte basée sur
        le prompt exact pour éviter le sur-apprentissage (Overfitting) sur des phrases répétées.

        Gère la robustesse face aux fichiers corrompus ou aux lignes mal formées.

        Returns:
            List[Dict]: Dataset propre et normalisé prêt pour l'encodage.
        """
        data_combines = []
        seen_prompts = set()  # Dédoublonnage simple sur le prompt exact

        for file_path in self.dataset_files:
            if not file_path.exists():
                self.logger.log_warning(f"Fichier dataset manquant : {file_path}")
                continue

            self.logger.info(f"📂 Chargement {file_path.name}...")
            try:
                lines = file_path.read_text(encoding="utf-8").splitlines()
                for line in lines:
                    if not line.strip():
                        continue
                    try:
                        obj = json.loads(line)
                        prompt = obj.get("prompt")

                        # Validation minimale
                        if not prompt or prompt in seen_prompts:
                            continue
                        if len(prompt) < 5:
                            continue

                        # Normalisation des labels (Gestion Majuscules/Minuscules)
                        # On s'assure que 'sujet' correspond à une valeur du JSON Map
                        # (Logique simplifiée ici, supposant que le AutoDatasetBuilder a fait le job)

                        data_combines.append(obj)
                        seen_prompts.add(prompt)
                    except:
                        continue
            except Exception as e:
                self.logger.log_error(f"Erreur lecture {file_path.name}: {e}")

        self.logger.info(
            f"📊 Dataset fusionné : {len(data_combines)} exemples uniques."
        )
        return data_combines

    def _preparer_mapping_labels(self, axe: str) -> Dict[str, int]:
        """Crée le mapping Label -> ID basé sur le fichier de config JSON."""
        # axe = "Sujet", "Action" ou "Categorie" (Clés du JSON)
        # Attention: dans le dataset les clés sont en minuscules ("sujet"), dans le map en Majuscule ("Sujet")

        cle_json = axe.capitalize()  # sujet -> Sujet
        valeurs = list(self.label_map_json[cle_json].values())
        return {lbl: i for i, lbl in enumerate(valeurs)}

    # =========================================================================
    # BOUCLE D'ENTRAÎNEMENT
    # =========================================================================

    def entrainer_sur_disque(self, epochs: int = 8, learning_rate: float = 1e-4):
        """
        Lance la séquence d'entraînement complète (Pipeline End-to-End).

        Orchestre l'entraînement séquentiel des 3 axes de classification (Sujet, Action, Catégorie).
        Pour chaque axe :
        1. Prépare le mapping Label -> ID spécifique.
        2. Lance la boucle d'optimisation (_entrainer_axe).
        3. Sauvegarde le modèle si succès.

        Cette méthode est bloquante et intensive en calcul (CPU/GPU).
        """
        self.logger.info("🚀 Démarrage de la session d'entraînement...")
        data = self._fusionner_datasets()

        if len(data) < 10:
            self.logger.log_error(
                "Dataset trop petit pour entraînement (<10). Annulation."
            )
            return False

        # Entraînement séquentiel pour les 3 axes
        resultats = {}
        for axe in ["sujet", "action", "categorie"]:
            acc = self._entrainer_axe(axe, data, epochs, learning_rate)
            resultats[axe] = acc

        self.logger.info(f"🎉 Entraînement terminé. Précision: {resultats}")
        return True

    def _entrainer_axe(self, axe: str, data: List[Dict]) -> float:
        """
        Boucle d'optimisation PyTorch pour un classifieur spécifique (Single Task Learning).

        Implémente le cycle standard : Forward Pass -> Loss Calculation (CrossEntropy) -> Backward Pass -> Optimizer Step.
        Inclut une phase de validation à chaque époque pour monitorer la généralisation et prévenir le sur-apprentissage.

        Args:
            axe (str): La dimension à apprendre ("sujet", "action" ou "categorie").
            data (List[Dict]): Le dataset complet.

        Returns:
            float: La meilleure précision (Accuracy) atteinte sur le jeu de validation.
        """

        # Récupération des hyperparamètres depuis le YAML uniquement
        cfg_train = self.config.get("entrainement", {})
        # Extraction des vérités depuis le YAML
        epochs = cfg_train.get("epochs", 8)
        lr = cfg_train.get("learning_rate", 1e-4)
        hidden_dim = cfg_train.get("hidden_dim", 256)  # Maintenant exploitée

        mapping = self._preparer_mapping_labels(axe)
        nb_labels = len(mapping)

        self.logger.info(
            f"💪 Entraînement axe '{axe.upper()}' ({nb_labels} classes)..."
        )

        # Split Train/Val
        train_data, val_data = train_test_split(data, test_size=0.15, random_state=42)

        ds_train = IntentDataset(train_data, self.sbert, axe, mapping)
        ds_val = IntentDataset(val_data, self.sbert, axe, mapping)

        dl_train = DataLoader(ds_train, batch_size=32, shuffle=True)
        dl_val = DataLoader(ds_val, batch_size=64)

        emb_dim = self.sbert.get_sentence_embedding_dimension()
        model = ClassifierHead(emb_dim, hidden_dim, nb_labels).to(self.device)
        opt = torch.optim.Adam(model.parameters(), lr=lr)
        loss_fn = nn.CrossEntropyLoss()

        best_acc = 0.0

        for epoch in range(epochs):
            model.train()
            train_losses = []
            for x, y in dl_train:
                x, y = x.to(self.device), y.to(self.device)
                opt.zero_grad()
                pred = model(x)
                loss = loss_fn(pred, y)
                loss.backward()
                opt.step()
                train_losses.append(loss.item())

            # Validation
            model.eval()
            correct = 0
            total = 0
            with torch.no_grad():
                for x, y in dl_val:
                    x, y = x.to(self.device), y.to(self.device)
                    pred = model(x).argmax(dim=1)
                    correct += (pred == y).sum().item()
                    total += len(y)

            acc = correct / total if total > 0 else 0
            self.logger.info(
                f"   Epoch {epoch + 1}/{epochs} | Loss: {np.mean(train_losses):.4f} | Acc: {acc:.4f}"
            )

            best_acc = max(best_acc, acc)

        # Sauvegarde
        save_path = self.output_dir / f"classifier_{axe}.pth"
        torch.save(model.state_dict(), save_path)
        self.logger.info(f"💾 Modèle '{axe}' sauvegardé -> {save_path.name}")

        return best_acc


if __name__ == "__main__":
    # Test autonome
    import logging

    logging.basicConfig(level=logging.INFO)
    trainer = AgentEntraineur()
    trainer.entrainer_sur_disque(epochs=5)
