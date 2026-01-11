# MoteurVecteurCode

Type : Infrastructure / Pipeline
Rôle principal : Transformer le code source brut en une base de connaissances vectorisée et structurée (RAG) pour permettre une recherche sémantique et une compréhension contextuelle profonde.
Portée : Globale
Statut : Stable

---

## Description fonctionnelle

Le MoteurVecteurCode est le pipeline d'indexation lourde du système. Il parcourt récursivement les dossiers du projet, analyse chaque fichier Python via des arbres de syntaxe abstraite (AST), extrait les relations entre les composants (graphe d'appels) et convertit ces informations en "chunks" sémantiques. Ces fragments sont ensuite vectorisés via SBERT et indexés dans une base de données FAISS pour une récupération instantanée.

---

## Objectifs

- Créer une représentation multidimensionnelle du code source (Vecteurs + Graphe + Squelette).
- Résoudre les dépendances internes (appels de méthodes, attributs de classe) pour tracer le flux logique.
- Générer un "Scripts Skeleton" (vue d'ensemble) optimisé pour l'injection dans les prompts LLM.

---

## Non-objectifs

Ce composant :
- N’a pas pour but de :
  - Effectuer de la recherche en temps réel (c'est le rôle de l'AgentCode).
  - Modifier ou refactoriser le code source.
  - Gérer les dépendances externes (bibliothèques tierces).

---

## Responsabilités

Ce composant est responsable de :
- Le scan exhaustif du projet en respectant strictement les filtres d'exclusion (backups, logs, caches).
- L'analyse syntaxique profonde : extraction des signatures, docstrings, types de retour et attributs `self`.
- La génération des fichiers d'architecture (`code_architecture.json`) et des chunks standardisés (`code_chunks.jsonl`).
- La construction et la sauvegarde de l'index FAISS et de ses métadonnées.

Ce composant n’est jamais responsable de :
- L'analyse d'autres langages que le Python (limitation actuelle du parser AST).

---

## Interfaces logiques

Expose :
- `run()` : Point d'entrée unique pour déclencher le cycle complet (Scan -> Analyse -> Index).
- `construire_index_vectoriel` : Interface de création de la base FAISS.

Consomme :
- `ContexteCode` (Dataclass) : Modèle de données pour la structure des fragments de code indexés.
- `SentenceTransformer` : Pour la génération des embeddings numériques.

---

## Invariants

- Purge préventive : Les anciens fichiers d'indexation sont systématiquement supprimés avant un nouveau scan pour éviter les données fantômes.
- Filtre de sécurité : Aucun fichier se trouvant dans un dossier marqué comme "backup" ou "archive" ne doit être indexé.

---

## Dépendances conceptuelles

Dépend de :
- Auditor : Pour la résolution des chemins racines et des dossiers de sortie.
- FAISS / SentenceTransformers : Pour la gestion de la base vectorielle.
- `ast` : Pour la déconstruction logique du code Python.

N’est jamais dépendant de :
- L'interface utilisateur ou les agents cognitifs.

---

## Contraintes connues

- Performance : Le scan peut être lent sur de très larges bases de code (plusieurs milliers de fichiers).
- Dépendance Windows : L'analyse des chemins est optimisée pour Windows (gestion des backslashes).

---

## Signaux d’interprétation pour l’IA

- Ce composant ne doit jamais être interprété comme :
  - Un agent capable de répondre à des questions (il prépare seulement les données).

- Si une ambiguïté apparaît :
  - Toujours se fier au fichier `scripts_skeleton.txt` pour avoir la vue la plus à jour de la structure du système.

- Ne jamais supposer que :
  - L'index vectoriel est à jour si la méthode `run()` n'a pas été appelée après une modification majeure du code.
