# AutoDatasetBuilder

Type : Pipeline
Rôle principal : Transformer les interactions en temps réel en données d'entraînement structurées pour le fine-tuning des modèles d'intentions.
Portée : Transversale
Statut : Stable

---

## Description fonctionnelle

L'AutoDatasetBuilder est le pipeline d'ingestion de données du système. Il agit comme un filtre de qualité (Gatekeeper) qui intercepte les interactions entre l'utilisateur et l'IA, les nettoie, et les sauvegarde au format JSONL. Ces données servent de base de vérité pour l'entraînement ultérieur du classifieur d'intentions SBERT via l'AgentEntraineur.

---

## Objectifs

- Automatiser la constitution de datasets d'entraînement à partir de l'usage réel.
- Garantir la qualité des données apprises en filtrant le bruit technique.
- Standardiser le format de sortie pour une compatibilité directe avec Sentence-Transformers.

---

## Non-objectifs

Ce composant :
- N’a pas pour but de :
  - Entraîner les modèles (rôle dévolu à l'AgentEntraineur).
  - Modifier le comportement de l'IA durant l'interaction.
  - Stocker l'historique conversationnel complet (uniquement les paires prompt/intention).

---

## Responsabilités

Ce composant est responsable de :
- Le nettoyage sémantique des textes (suppression des sauts de ligne, espaces superflus).
- L'application des critères de qualification (longueurs minimales, blacklist de commandes).
- La validation de la certitude des intentions avant archivage.
- L'écriture atomique des entrées dans le fichier `batch_dataset.jsonl`.

Ce composant n’est jamais responsable de :
- La correction manuelle des erreurs de classification.

---

## Interfaces logiques

Expose :
- `ajouter_interaction(interaction)` : Point d'entrée pour soumettre un échange au pipeline d'ingestion.

Consomme :
- `Interaction` (Dataclass) : Pour extraire le prompt et l'intention associée.
- `CustomJSONEncoder` : Pour sérialiser proprement les Enums sémantiques.

---

## Invariants

- Intégrité : Aucune interaction classée comme "Inconnue" par le système ne doit être intégrée au dataset.
- Format : Chaque entrée doit être une ligne JSON unique (JSONL) pour permettre une lecture incrémentale.
- L’AutoDatasetBuilder extrait volontairement et exclusivement le prompt et l’intention depuis Interaction, car ces champs constituent l’unité minimale requise pour l’entraînement du IntentionDetector.
Tous les autres champs de Interaction sont hors périmètre de ce composant.
---

## Dépendances conceptuelles

Dépend de :
- `AgentBase` : Pour l'accès aux services de logging et de supervision.
- `contrats_interface` : Pour la structure des objets `Interaction` et `ResultatIntention`.

N’est jamais dépendant de :
- `MoteurLLM` : Il traite uniquement des données déjà produites.

---

## Contraintes connues

- Limite de caractères : Les prompts sont tronqués à 2000 caractères pour optimiser les performances de SBERT.
- Chemin fixe : Le chemin du dataset est actuellement codé en dur vers le `data_training_center`.

---

## Signaux d’interprétation pour l’IA

- Ce composant ne doit jamais être interprété comme :
  - Un module de mémoire (il ne sert qu'à l'entraînement futur).

- Si une ambiguïté apparaît :
  - Prioriser le rejet d'une interaction douteuse plutôt que de risquer de polluer le dataset.

- Ne jamais supposer que :
  - Une donnée ajoutée au dataset est immédiatement utilisée par le classifieur d'intentions.
