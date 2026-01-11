# GardienProjet

Type : Système
Rôle principal : Surveiller en temps réel les modifications des fichiers sources et déclencher les procédures d'audit ou de ré-indexation nécessaires.
Portée : Globale
Statut : Stable

---

## Description fonctionnelle

Le GardienProjet est un service de surveillance (watchdog) qui s'assure de l'intégrité et de la synchronisation du système. Il s'appuie sur une "Project Map" dynamique pour identifier les fichiers critiques à surveiller. En cas de modification d'un fichier Python, il peut automatiquement déclencher une mise à jour de l'index de code via l'AgentCode ou initier un audit de sécurité via l'AgentAuditor.

---

## Objectifs

- Assurer une ré-indexation automatique du code dès qu'un fichier est modifié pour maintenir la pertinence du RAG.
- Déclencher des audits de sécurité immédiats sur les fichiers d'agents modifiés.
- Synchroniser périodiquement les statistiques du système avec le backend.

---

## Non-objectifs

Ce composant :
- N’a pas pour but de :
  - Empêcher physiquement l'écriture sur le disque.
  - Gérer le versionnage (Git) des fichiers.
  - Exécuter du code utilisateur.

---

## Responsabilités

Ce composant est responsable de :
- Surveiller le répertoire `agentique` de manière récursive.
- Charger et rafraîchir dynamiquement la liste des fichiers surveillés (whitelist) via `project_map.json`.
- Déclencher `AgentCode.rafraichir_index()` lors de modifications sur des fichiers `.py` validés.
- Appeler `AgentAuditor.auditer_securite_fichier()` pour les composants critiques (préfixe `agent_`).
- Envoyer des requêtes de synchronisation de statistiques au backend toutes les 5 minutes.

Ce composant n’est jamais responsable de :
- La correction des erreurs détectées lors de l'audit.

---

## Interfaces logiques

Expose :
- `start()` : Lance l'observateur de fichiers et le thread de synchronisation des statistiques.
- `stop()` : Arrête proprement les services de surveillance.

Consomme :
- `AgentCode` : Pour la mise à jour de la vision vectorielle du code.
- `AgentAuditor` : Pour la validation de la conformité des agents modifiés.
- `project_map.json` : Pour la définition dynamique de la portée de surveillance.

---

## Invariants

- Seuls les fichiers présents dans la whitelist issue de la Project Map déclenchent des actions.
- Les fichiers générés par l'indexation (ex: `code_chunks`) sont ignorés pour éviter les boucles infinies de surveillance.

---

## Dépendances conceptuelles

Dépend de :
- `Watchdog` : Pour la détection des événements du système de fichiers.
- `Requests` : Pour la communication avec l'API de statistiques.
- `Threading` : Pour l'exécution non bloquante des tâches de fond.

N’est jamais dépendant de :
- L'interface utilisateur (fonctionne comme un service daemon).

---

## Contraintes connues

- Nécessite des droits d'accès en lecture sur l'arborescence du projet et en écriture pour les logs d'audit.
- La ré-indexation automatique peut consommer des ressources CPU significatives lors de modifications massives de fichiers.

---

## Signaux d’interprétation pour l’IA

- Ce composant ne doit jamais être interprété comme :
  - Un système de backup (il ne sauvegarde pas les anciennes versions).

- Si une ambiguïté apparaît :
  - Vérifier la validité du chemin `PATH_TO_WATCH` et l'existence du fichier `project_map.json`.

- Ne jamais supposer que :
  - Le Gardien peut réparer un fichier corrompu ; il ne fait que signaler l'anomalie.
