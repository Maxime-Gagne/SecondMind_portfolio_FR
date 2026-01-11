# AgentEntraineur

Type : Support / Gouvernance
Responsabilité primaire : Superviser l'apprentissage du système en fusionnant les jeux de données et en entraînant les classifieurs d'intentions (SBERT).
Statut : Stable

---

## Rôle fonctionnel

- Fonction principale : Orchestre le pipeline complet d'entraînement des modèles de classification d'intentions, de la préparation des données à la validation des performances.
- Problème résolu : Assure que le système s'adapte aux nouvelles requêtes de l'utilisateur en mettant à jour ses capacités de détection sémantique.
- Résultat produit : Fichiers de poids neuronaux (.pth) optimisés pour les trois axes de classification (Sujet, Action, Catégorie).

---

## Périmètre

L’agent :
- Fait :
  - Fusionne et dédoublonne les sources de données (dataset manuel, généré par batch, et données live).
  - Gère l'architecture du réseau de neurones (ClassifierHead) pour le mapping des embeddings SBERT.
  - Exécute les boucles d'entraînement PyTorch (Adam Optimizer, CrossEntropyLoss).
  - Effectue le découpage Train/Validation (85/15) pour garantir la capacité de généralisation.
  - Sauvegarde automatiquement les modèles validés dans le répertoire de production.

- Ne fait jamais :
  - N'entraîne le modèle de base (SentenceTransformer) ; il se concentre uniquement sur les têtes de classification.
  - Ne déploie les modèles si la précision de validation est jugée insuffisante.

---

## Contrat logique

### Entrées attendues
- Datasets JSONL : Fichiers contenant les paires (prompt, classification) pour l'apprentissage.
- Label Map JSON : Définition officielle des classes autorisées pour chaque axe.
- Configuration SBERT : Chemins des modèles de base et paramètres d'entraînement.

### Sorties garanties
- Modèles .pth : Poids entraînés pour chaque classifieur (Sujet, Action, Catégorie).
- Rapports de précision : Scores de Loss et Accuracy pour chaque époque d'entraînement.

---

## Invariants

- Seuil de donnée : L'entraînement est systématiquement annulé si le dataset fusionné comporte moins de 10 exemples uniques.
- Dédoublonnage : Les prompts identiques ou de moins de 5 caractères sont automatiquement ignorés.
- Cohérence Matérielle : L'agent détecte et utilise prioritairement CUDA (GPU) pour l'entraînement, avec un fallback automatique sur CPU.

---

## Dépendances conceptuelles

Dépend de :
- MoteurMiniLLM : Pour la configuration des modèles et des chemins de sortie.
- Auditor : Pour la localisation des fichiers de configuration et des datasets.
- SentenceTransformer : Pour la génération des vecteurs d'entrée (embeddings).

N’est jamais dépendant de :
- AgentParole : Il n'intervient pas dans la construction des réponses en temps réel.

---

## Modes d’échec connus

- Si un fichier dataset est corrompu ou illisible → alors l'agent logue un avertissement et continue avec les sources valides restantes.
- Si le GPU manque de mémoire (OOM) → l'entraînement peut échouer (nécessite une réduction du batch_size dans le code).

---

## Signaux d’interprétation pour l’IA

- Cet agent ne doit jamais être utilisé pour :
  - Classifier des intentions en temps réel (utiliser l'IntentionDetector pour cela).

- Si une action semble ambiguë :
  - Toujours privilégier la qualité du dataset manuel sur les données générées automatiquement.

- Ne jamais supposer que :
  - Un modèle est prêt pour la production sans avoir vérifié les logs de précision finale.
