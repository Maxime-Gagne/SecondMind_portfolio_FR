#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AutoDatasetBuilder - Pipeline d'Acquisition Automatique de Données (Data Engineering)
Module responsable de la transformation des interactions conversationnelles en datasets d'entraînement pour le ML.

Ce module agit comme un filtre de qualité (Quality Gate) entre le flux de production (Runtime)
et le flux d'apprentissage (Training). Il garantit que seules les données pertinentes, propres
et significatives sont injectées dans la base d'entraînement du classifieur d'intentions.

Stratégie "Data-Centric AI" :
    Plutôt que d'améliorer le modèle (SBERT), on améliore d'abord la donnée qui le nourrit.
    Le module applique des règles heuristiques strictes pour éliminer le bruit, les commandes système
    et les hallucinations potentielles.
"""

import json
import re
from pathlib import Path
from datetime import datetime
from agentique.base.META_agent import AgentBase
from agentique.base.contrats_interface import Interaction
from typing import Dict, Any, Optional
from agentique.base.META_agent import AgentBase
from agentique.base.contrats_interface import (
    ResultatIntention,
    CustomJSONEncoder,
)  # ✅ AJOUT Encoder


class AutoDatasetBuilder(AgentBase):
    def __init__(self):
        super().__init__(nom_agent="AutoDatasetBuilder")
        """
        Ingénieur de données autonome.

        Cette classe gère l'append-only sur le fichier `batch_dataset.jsonl`. Elle est stateless
        mais applique une politique de filtrage configurée en dur (Blacklist, Min/Max length)
        pour protéger le futur modèle contre la pollution des données.

        Attributes:
            dataset_path (Path): Chemin physique du fichier JSONL accumulant les connaissances.
            MIN_CHARS, MIN_WORDS (int): Seuils minimaux de richesse sémantique.
        """

        # Chemin du dataset (Source de vérité pour l'entraînement)
        self.dataset_path = Path(
            r"D:\rag_personnel\data_training_center\Semi\intention_detector_SBERT\dataset\batch_dataset.jsonl"
        )
        self.dataset_path.parent.mkdir(parents=True, exist_ok=True)

        # --- CRITÈRES DE QUALITÉ ---
        self.MIN_CHARS = 10  # Ex: "C'est quoi?" (11 chars) est limite mais ok
        self.MIN_WORDS = 3  # Ex: "Analyse ce fichier" (3 mots)
        self.MAX_CHARS = 2000  # Pour éviter de noyer SBERT avec un livre entier

        # Commandes à bannir (Bruit technique)
        self.BLACKLIST_STARTS = [
            "+1",
            "-1",
            "!!!",
            "recherche_web",
            "rechercher_memoire",
            "exit",
            "quit",
        ]

    def _nettoyer_texte(self, texte: str) -> str:
        """
        Normalisation textuelle pour l'entraînement SBERT.

        SBERT performe mieux sur des phrases canoniques. Cette méthode :
        1. Élimine les sauts de ligne excessifs et les tabulations (Flattening).
        2. Réduit les espaces multiples à un espace simple.
        3. Trim les espaces début/fin.

        Args:
            texte (str): Le prompt brut de l'utilisateur.

        Returns:
            str: Le texte nettoyé prêt pour le dataset.
        """
        if not texte:
            return ""
        # Remplace les sauts de ligne multiples et tabulations par un espace simple
        # (SBERT préfère souvent une ligne continue ou des paragraphes propres)
        texte = re.sub(r"\s+", " ", texte).strip()
        return texte

    def _est_qualifie(self, prompt: str, intention: Any) -> bool:
        """
        Le "Quality Gate" (Porte de Qualité).

        Décide si une interaction mérite d'être apprise par le système.
        Critères de rejet :
        - **Bruit Technique** : Commandes système (+1, !!!, exit).
        - **Pauvreté Sémantique** : Prompts trop courts (< 10 chars ou < 3 mots).
        - **Incertitude** : Interactions classées comme "INCONNU" (on n'apprend pas l'ignorance).

        Args:
            prompt (str): Le texte nettoyé.
            intention (Any): La classification proposée par le système.

        Returns:
            bool: True si la donnée est valide pour le Fine-Tuning.
        """
        if not prompt or not intention:
            return False

        # 1. Filtre Commandes Système
        for blocked in self.BLACKLIST_STARTS:
            if prompt.startswith(blocked):
                return False

        # 2. Filtre Longueur
        if len(prompt) < self.MIN_CHARS:
            return False

        if len(prompt.split()) < self.MIN_WORDS:
            return False

        # 3. Filtre Incertitude (Si l'IA a classé comme INCONNU, on n'apprend pas cette bêtise)
        # Note: On suppose que 'intention' est un objet ResultatIntention ou un dict
        try:
            # Gestion objet vs dict
            sujet = (
                intention.sujet.value
                if hasattr(intention, "sujet")
                else intention.get("sujet")
            )
            if sujet and "inconnu" in sujet.lower():
                return False
        except:
            pass  # Si on ne peut pas lire, dans le doute on garde si le texte est bon

        return True

    def ajouter_interaction(
        self, interaction: Interaction, source: str = "batch"
    ) -> bool:
        """
        Point d'entrée principal pour l'ingestion de données.

        Orchestre le pipeline complet :
        1. **Nettoyage** : Appel à _nettoyer_texte.
        2. **Filtrage** : Appel à _est_qualifie. Si rejeté, logge l'info et arrête.
        3. **Troncature** : Coupe les textes trop longs (> 2000 chars) pour respecter la fenêtre de contexte SBERT.
        4. **Extraction** : Crée un objet `ResultatIntention` propre.
        5. **Persistance** : Ajoute la ligne JSONL au fichier dataset (Append-Only).

        Args:
            interaction (Interaction): L'objet source contenant prompt et intention.
            source (str): Métadonnée de provenance (ex: "batch", "manual_correction").

        Returns:
            bool: True si l'ajout a été effectué avec succès.
        """
        try:
            # 1. Nettoyage
            prompt_clean = self._nettoyer_texte(interaction.prompt)

            # 2. Validation Qualité (Le Gatekeeper)
            if not self._est_qualifie(prompt_clean, interaction.intention):
                # ✅ CORRECTION : Log de rejet ici, et retour False immédiat
                # On utilise INFO pour ne pas spammer les logs d'erreurs avec des rejets normaux
                self.logger.info(
                    f"📉 Interaction rejetée (Filtre Qualité) : {prompt_clean[:50]}..."
                )
                return False

            # 3. Troncature intelligente
            if len(prompt_clean) > self.MAX_CHARS:
                prompt_clean = prompt_clean[: self.MAX_CHARS]

            # 4. Extraction des données
            nouvelle_donnee = ResultatIntention(
                prompt=prompt_clean,
                sujet=interaction.intention.sujet,
                action=interaction.intention.action,
                categorie=interaction.intention.categorie,
            )

            # 5. Écriture Append (JSONL)
            with open(self.dataset_path, "a", encoding="utf-8") as f:
                # ✅ AJOUT cls=CustomJSONEncoder pour transformer les Enums en strings
                json.dump(nouvelle_donnee, f, ensure_ascii=False, cls=CustomJSONEncoder)
                f.write("\n")

            self.logger.info(f"📈 Dataset enrichi (+1) : {prompt_clean[:30]}...")
            return True

        except Exception as e:
            self.logger.log_error(f"Erreur ajout dataset : {e}")
            return False
