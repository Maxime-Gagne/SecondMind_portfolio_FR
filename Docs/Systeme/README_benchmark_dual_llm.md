# Benchmark Dual LLM

Type : Interface / Système
Rôle principal : Mesurer et comparer les performances techniques brutes du moteur principal (14B) et du moteur mini (1.5B) au sein du pipeline.
Portée : Globale
Statut : Stable

---

## Description fonctionnelle

Le Benchmark Dual LLM est un laboratoire de test de performance intégré. Il permet de quantifier les capacités de génération (tokens par seconde), la latence de premier token (TTFT) et la consommation de ressources (VRAM) pour chaque modèle individuellement ou pour le pipeline complet (RAG + Classification + Génération). Il fournit une visualisation graphique en temps réel et un historique des sessions pour optimiser la configuration matérielle et logicielle.

---

## Objectifs

- Évaluer objectivement la vitesse de traitement des différents moteurs LLM locaux.
- Identifier les goulots d'étranglement dans le pipeline complet (temps de classification vs temps de génération).
- Monitorer l'usage de la mémoire vidéo (VRAM) sur le matériel hôte (ex: RTX 3090).

---

## Non-objectifs

Ce composant :
- N’a pas pour but de :
  - Juger la qualité sémantique ou la véracité des réponses (rôle de l'AgentJuge).
  - Gérer l'entraînement ou le fine-tuning des modèles.

---

## Responsabilités

Ce composant est responsable de :
- L'exécution de requêtes de test calibrées vers les points de terminaison `/api/benchmark`.
- Le calcul précis des métriques temporelles (latence inter-token, TTFT, débit global).
- La récupération des statistiques matérielles via NVML sur le backend.
- La mise à jour dynamique des graphiques de performance via Chart.js.
- La persistance locale de l'historique des tests dans `benchmark_history.jsonl`.

Ce composant n’est jamais responsable de :
- La modification des fichiers de configuration LLM (délégué au dashboard de configuration).

---

## Interfaces logiques

Expose :
- `Interface Web (Lab)` : Cockpit de pilotage des tests avec graphiques temps réel.
- `API /api/benchmark/full_pipeline` : Mesure le flux complet de l'intention à la réponse.

Consomme :
- `MoteurLLM` & `MoteurMiniLLM` : Fournissent les flux de tokens nécessaires aux mesures.
- `NVML (NVIDIA Management Library)` : Fournit l'état précis de la VRAM.
- `Chart.js` : Assure le rendu visuel des tendances de performance.

---

## Invariants

- Les mesures de "Tokens par seconde" doivent être calculées uniquement sur le temps de génération pur, après réception du premier token.
- L'usage VRAM rapporté doit être la valeur instantanée au moment du pic de génération.

---

## Dépendances conceptuelles

Dépend de :
- `Backend Hermes` : Pour l'exposition des routes de benchmark et l'accès au GPU.
- `Chart.js` : Indispensable pour la visualisation graphique.

N’est jamais dépendant de :
- La connexion Internet (tous les benchmarks s'exécutent sur l'infrastructure locale).

---

## Contraintes connues

- La précision des mesures peut varier en fonction de la charge globale du système (processus tiers sur le GPU).
- Nécessite un environnement NVIDIA fonctionnel pour la remontée des statistiques VRAM.

---

## Signaux d’interprétation pour l’IA

- Ce composant ne doit jamais être interprété comme :
  - Un simple outil décoratif ; ses données servent à valider la viabilité technique du système.

- Si une ambiguïté apparaît :
  - Toujours se fier à la métrique `ttft_ms` pour évaluer la réactivité perçue par l'utilisateur.

- Ne jamais supposer que :
  - Un score élevé en tokens/sec garantit la pertinence de la réponse générée.
