# Documentation Technique (RAG Module)

Type : Pipeline / Système
Rôle principal : Scrapper, indexer et servir une base de connaissances technique via un moteur de recherche vectoriel (FAISS).
Portée : Globale
Statut : Stable

---

## Description fonctionnelle

Ce module constitue la base de connaissances spécialisée du système SecondMind. Il automatise la collecte de documentations techniques web, leur transformation en vecteurs sémantiques (embeddings) et leur stockage dans un index haute performance. Il expose ensuite ces données via une interface de recherche web et une API, permettant aux agents de consulter des documentations complexes (ex: HuggingFace, Pydantic) pour résoudre des problèmes de programmation.

---

## Objectifs

- Créer une bibliothèque de documentation technique consultable localement et hors-ligne.
- Permettre une recherche par similarité sémantique (Cosine Similarity) plutôt que par mots-clés simples.
- Fournir une interface de consultation humaine pour valider la pertinence des données scrapées.

---

## Non-objectifs

Ce composant :
- N’a pas pour but de :
  - Servir de navigateur web généraliste.
  - Remplacer la mémoire de travail des agents (il fournit uniquement le contexte externe).
  - Gérer l'entraînement de nouveaux modèles de langage.

---

## Responsabilités

Ce composant est responsable de :
- Extraire le contenu textuel utile des pages HTML en ignorant les éléments parasites (nav, footer, scripts).
- Découper les textes longs en fragments (chunks) sémantiques cohérents.
- Générer des embeddings vectoriels de dimension 384 via le modèle `all-MiniLM-L6-v2`.
- Maintenir et sauvegarder l'index FAISS (`documentation.faiss`) et ses métadonnées.
- Fournir une API Flask pour interroger la base en temps réel.

Ce composant n’est jamais responsable de :
- La mise à jour automatique des URLs sources (le mapping doit être fourni en entrée).

---

## Interfaces logiques

Expose :
- `API /api/search` : Permet de soumettre une requête textuelle et de recevoir les $k$ fragments les plus pertinents.
- `Interface Web (Port 5000)` : Visualisation humaine des statistiques de la base et test des recherches.

Consomme :
- `HuggingFace Sentence-Transformers` : Pour la vectorisation du texte.
- `FAISS (Facebook AI Similarity Search)` : Pour l'indexation et la recherche vectorielle rapide.

---

## Invariants

- L'index FAISS et le fichier de métadonnées JSON doivent toujours être synchronisés (même nombre d'entrées).
- Les vecteurs stockés doivent être normalisés (L2) pour garantir la validité de la similarité cosinus.

---

## Dépendances conceptuelles

Dépend de :
- `Sentence-Transformers` : Crucial pour transformer le texte brut en données mathématiques exploitables.
- `BeautifulSoup4` : Pour le nettoyage et le parsing des structures HTML.

N’est jamais dépendant de :
- `AgentSemi` : Ce module est autonome et peut être utilisé comme un outil de recherche indépendant.

---

## Contraintes connues

- Le scraping est limité par les politiques de `User-Agent` et la structure changeante des sites web ciblés.
- La recherche est limitée aux packages préalablement indexés dans le fichier de mapping.

---

## Signaux d’interprétation pour l’IA

- Ce composant ne doit jamais être interprété comme :
  - Une base de données relationnelle (SQL). Les résultats sont basés sur la proximité sémantique, pas sur une correspondance exacte.

- Si une ambiguïté apparaît :
  - Se référer aux statistiques (`documentation_stats.json`) pour vérifier la fraîcheur et la taille de la base.

- Ne jamais supposer que :
  - Le scraper peut contourner des Paywalls ou des protections anti-bot complexes (Cloudflare, etc.).
