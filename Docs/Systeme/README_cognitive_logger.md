# CognitiveLogger

Type : Système
Rôle principal : Centraliser et structurer les journaux d'événements (logs) cognitifs et techniques pour chaque agent du système.
Portée : Globale
Statut : Stable

---

## Description fonctionnelle

Le CognitiveLogger est un moteur de journalisation hybride qui combine le logging standard Python avec une sortie structurée en format JSONL. Il est conçu pour capturer non seulement les erreurs techniques, mais aussi le flux de "pensée" (thoughts), les interactions et les appels API des agents. Il s'appuie sur l'Auditor pour résoudre dynamiquement les chemins de stockage des fichiers de log.

---

## Objectifs

- Fournir une traçabilité complète des processus cognitifs d'un agent pour le débogage et l'audit.
- Standardiser le format des logs (JSONL) pour permettre une analyse automatisée ultérieure.
- Assurer une séparation étanche des journaux par agent et par session via des IDs uniques.

---

## Non-objectifs

Ce composant :
- N’a pas pour but de :
  - Gérer l'affichage en temps réel sur une interface utilisateur complexe (limité à la console).
  - Garantir la persistance à long terme ou l'archivage (limité à l'écriture locale).

---

## Responsabilités

Ce composant est responsable de :
- L'initialisation sécurisée des répertoires de logs en consultant l'Auditor.
- La capture et le formatage des interactions, pensées, erreurs et avertissements.
- La gestion des IDs de session et de corrélation pour le suivi des requêtes.
- L'émission de signaux de gouvernance de haute priorité en cas d'anomalies critiques.

Ce composant n’est jamais responsable de :
- La décision de couper ou de modifier le flux d'exécution d'un agent.

---

## Interfaces logiques

Expose :
- `log_thought(thought_text)` : Enregistre le cheminement interne de l'agent.
- `log_interaction(role, message)` : Journalise les échanges (U/A).
- `log_error(error_msg)` : Capture les échecs avec support des exceptions.
- `signal_gouvernance(message)` : Alerte sur des violations de règles système.

Consomme :
- `Auditor` : Pour la résolution des chemins de fichiers standards.
- `Python Logging` : Pour la gestion des handlers console et fichiers.

---

## Invariants

- Chaque entrée JSONL doit inclure un `timestamp` au format ISO et le nom de l'agent source.
- Le logger doit rester fonctionnel (mode console) même si l'accès au système de fichiers échoue.

---

## Dépendances conceptuelles

Dépend de :
- `JSON` & `UUID` : Pour la structure des données et l'identification des sessions.
- `Pathlib` : Pour la manipulation robuste des chemins.

N’est jamais dépendant de :
- Une base de données externe : il écrit directement sur le disque local.

---

## Contraintes connues

- Le logging vers fichier est automatiquement désactivé si le répertoire cible (fourni par l'auditor) n'existe pas.
- L'écriture dans le fichier JSONL est synchrone, ce qui peut impacter légèrement les performances lors d'écritures massives.

---

## Signaux d’interprétation pour l’IA

- Ce composant ne doit jamais être interprété comme :
  - Une mémoire persistante (les logs sont des traces, pas des connaissances).

- Si une ambiguïté apparaît :
  - Vérifier si l'Auditor est correctement passé lors de l'instanciation pour activer le mode fichier.

- Ne jamais supposer que :
  - Le `session_id` est persistant entre deux redémarrages complets de l'application (sauf si injecté explicitement).
