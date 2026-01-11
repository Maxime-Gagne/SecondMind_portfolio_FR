# IntentionDetector

Type : Système
Rôle principal : Classifier l'intention de l'utilisateur selon trois axes (Sujet, Action, Catégorie) à l'aide de modèles SBERT et PyTorch.
Portée : Locale
Statut : Stable

---

## Description fonctionnelle

L'IntentionDetector est un moteur de classification sémantique "zéro hardcode" piloté par configuration YAML. Il utilise une architecture hybride : un encodeur Sentence-Transformer (SBERT) pour générer des embeddings vectoriels, suivis de trois têtes de classification MLP (Multi-Layer Perceptron) distinctes pour prédire les étiquettes taxonomiques. Il prend en compte un historique glissant de la conversation pour contextualiser la détection.

---

## Objectifs

- Extraire de manière structurée l'intention derrière un prompt utilisateur.
- Garantir une classification rapide et déterministe grâce à des modèles locaux.
- Assurer la cohérence des sorties via le respect strict des enums de l'interface (`Sujet`, `Action`, `Categorie`).

---

## Non-objectifs

Ce composant :
- N’a pas pour but de :
  - Générer des réponses textuelles pour l'utilisateur.
  - Entraîner les modèles (les poids `.pth` doivent être pré-existants).
  - Gérer la mémoire à long terme (limité aux derniers échanges).

---

## Responsabilités

Ce composant est responsable de :
- Charger les modèles SBERT et les trois classifieurs PyTorch au démarrage.
- Prétraiter le prompt en fusionnant l'historique récent pour créer un contexte textuel.
- Prédire les index de classes et les convertir en valeurs humaines via un `label_map.json`.
- Valider le format de sortie via l'Auditor pour garantir le respect du contrat d'interface.

Ce composant n’est jamais responsable de :
- La décision logique de ce qu'il faut faire après la détection (ce rôle incombe à l'orchestrateur).

---

## Interfaces logiques

Expose :
- `intention_detector(prompt, historique_brut)` : Retourne un objet `ResultatIntention` contenant les enums classifiés.

Consomme :
- `SentenceTransformer` : Pour la vectorisation du texte.
- `Auditor` : Pour la récupération des chemins de configuration et la validation des sorties.
- `label_map.json` : Pour la correspondance entre index numériques et labels textuels.

---

## Invariants

- Les trois classifieurs doivent toujours être chargés simultanément.
- La sortie doit obligatoirement correspondre aux Enums définis dans `contrats_interface`.
- Le calcul doit être effectué sur le `device` (CPU/CUDA) spécifié dans le YAML.

---

## Dépendances conceptuelles

Dépend de :
- `PyTorch` : Pour l'exécution des têtes de classification.
- `Sentence-Transformers` : Pour l'encodage sémantique.
- `YAML` : Pour l'injection des chemins et paramètres.

N’est jamais dépendant de :
- Un service LLM distant (fonctionne à 100% en local).

---

## Contraintes connues

- Nécessite l'existence préalable de trois fichiers `.pth` (sujet, action, catégorie) dans le dossier des modèles.
- Sensible à la qualité du `label_map.json` ; toute désynchronisation entre l'entraînement et l'inférence faussera les résultats.

---

## Signaux d’interprétation pour l’IA

- Ce composant ne doit jamais être interprété comme :
  - Un simple parseur de mots-clés (il utilise une compréhension vectorielle).

- Si une ambiguïté apparaît :
  - Vérifier si l'historique de conversation n'a pas "pollué" l'embedding du prompt actuel.

- Ne jamais supposer que :
  - Le détecteur peut inventer de nouvelles catégories (il est strictement limité à sa taxonomie entraînée).
