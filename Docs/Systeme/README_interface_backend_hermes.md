# Backend Hermes

Type : Système
Rôle principal : Agir comme le système nerveux central (API & Orchestrateur) pour l'interface utilisateur, la gestion des agents et le monitoring système.
Portée : Globale
Statut : Stable

---

## Description fonctionnelle

Le Backend Hermes est un serveur Flask/SocketIO robuste qui orchestre les interactions entre l'interface utilisateur (Hub, IDE, Benchmark) et le cerveau cognitif (AgentSemi). Il gère le cycle de vie des conversations, l'exposition des routes API pour le système de fichiers, la transcription audio via Whisper, et le monitoring des ressources matérielles (GPU/VRAM). Il intègre également un système de sauvegarde atomique pour garantir l'intégrité des données en cas de crash.

---

## Objectifs

- Centraliser l'accès aux capacités des agents via une API REST et WebSocket sécurisée.
- Assurer la persistance structurée des conversations et des métadonnées associées.
- Fournir des services d'infrastructure (Audit, Monitoring GPU, Synchronisation de stats) aux autres modules.

---

## Non-objectifs

Ce composant :
- N’a pas pour but de :
  - Gérer l'entraînement direct des modèles (délégué au DataCenter).
  - Fournir une interface graphique (il ne fait que servir les fichiers statiques).

---

## Responsabilités

Ce composant est responsable de :
- L'instanciation et la supervision de l'AgentSemi et du GardienProjet.
- La gestion du streaming des réponses LLM via des générateurs HTTP.
- La gestion sécurisée des fichiers de conversation (sauvegarde atomique .tmp -> .json).
- La transcription audio temps réel via l'intégration du modèle Whisper.
- L'exposition des métriques de performance pour le "Benchmark Lab".
- Le filtrage intelligent des logs pour maintenir une console propre.

Ce composant n’est jamais responsable de :
- La logique d'inférence pure (délégué aux serveurs llama-server distants ou locaux).

---

## Interfaces logiques

Expose :
- `POST /command` : Point d'entrée principal pour l'interaction textuelle (Streaming).
- `GET /api/status` : Télémétrie de santé du système.
- `Socket.IO` : Canal bidirectionnel pour le monitoring live (VRAM, Prompt Viewer).
- `ConversationManager` : API de gestion CRUD pour l'historique des discussions.

Consomme :
- `AgentSemi` : Pour le traitement cognitif des requêtes.
- `NVML` : Pour la récupération des statistiques GPU.
- `Whisper API` : Pour la conversion Speech-to-Text.

---

## Invariants

- Le serveur doit valider la conformité des encodages de fichiers via l'AgentAuditor au démarrage.
- Aucune écriture dans les fichiers de métadonnées ne doit se faire sans passer par le protocole de sauvegarde atomique (fsync).

---

## Dépendances conceptuelles

Dépend de :
- `Flask` & `SocketIO` : Pour la couche transport et réseau.
- `PyTorch / Whisper` : Pour les capacités de transcription audio.
- `GardienProjet` : Pour la synchronisation automatique des statistiques.

N’est jamais dépendant de :
- Un moteur de base de données externe (utilise le système de fichiers local JSON/YAML).

---

## Contraintes connues

- Limité à un déploiement local (0.0.0.0:3000) sans couche d'authentification utilisateur native.
- Nécessite l'installation de FFmpeg pour la partie transcription audio.

---

## Signaux d’interprétation pour l’IA

- Ce composant ne doit jamais être interprété comme :
  - Un simple serveur de fichiers statiques ; il contient la logique de routage sémantique.

- Si une ambiguïté apparaît :
  - Vérifier les logs filtrés pour détecter des échecs de synchronisation de statistiques.

- Ne jamais supposer que :
  - Le backend peut fonctionner sans la racine du projet correctement injectée dans le `sys.path` via `config_paths`.
