# AuditorBase

Type : Système
Rôle principal : Agir comme le gardien de la conformité, validant les standards de structure, les chemins et les contrats de données entre les agents.
Portée : Globale
Statut : Stable

---

## Description fonctionnelle

L'AuditorBase est le pivot central de la gouvernance du système. Il centralise la définition des standards pour chaque agent (chemins, configurations, formats de sortie autorisés) et fournit des outils de validation runtime. Contrairement à d'autres agents, il ne crée aucun dossier mais vérifie l'intégrité des structures existantes et la validité profonde des échanges de données (Deep Type Checking) via des Dataclasses.

---

## Objectifs

- Garantir que chaque agent respecte sa topologie de fichiers et sa configuration définie.
- Assurer l'intégrité des contrats d'interface lors des échanges inter-agents.
- Détecter et persister les violations de format ou de type en temps réel.

---

## Non-objectifs

Ce composant :
- N’a pas pour but de :
  - Créer des répertoires ou modifier l'arborescence système (Audit passif).
  - Exécuter de la logique métier ou de l'inférence LLM.

---

## Responsabilités

Ce composant est responsable de :
- Fournir les chemins absolus officiels aux agents via la racine du projet (`ROOT_DIR`).
- Valider les formats d'entrée et de sortie selon les standards déclarés par agent.
- Effectuer une validation récursive des champs de Dataclass pour assurer la conformité des types.
- Tracer les violations et les champs ignorés via un système de log JSONL (`runtime_violations.jsonl`).

Ce composant n’est jamais responsable de :
- La correction automatique des données invalides.

---

## Interfaces logiques

Expose :
- `get_path(path_type, nom_agent)` : Récupère le chemin configuré pour un type spécifique.
- `valider_format_sortie(data)` : Vérifie si un objet produit respecte le standard de l'agent.
- `valider_utilisation_complete(objet)` : Détecte les champs vides ou non accédés dans une structure.

Consomme :
- `StandardsAgents` : La classe contenant les définitions statiques de chaque agent.
- `ROOT_DIR` : La constante racine pour la résolution des chemins.

---

## Invariants

- L'AuditorBase ne doit jamais instancier de logger avant sa propre initialisation pour éviter les dépendances circulaires.
- Toute violation détectée doit être persistée de manière asynchrone dans le journal des violations.
- Les erreurs détectées durant la phase d’initialisation (bootstrap) sont rapportées via la console standard ; la journalisation persistante n’est garantie qu’après l’injection complète du CognitiveLogger.
---

## Dépendances conceptuelles

Dépend de :
- `Dataclasses` : Pour l'inspection des formats d'échange.
- `Pathlib` : Pour la manipulation sécurisée des chemins de fichiers.

N’est jamais dépendant de :
- `MetaAgent` : Il doit rester autonome pour être utilisé par la base des agents sans circularité.

---

## Contraintes connues

- La liste des agents et leurs chemins doivent être déclarés manuellement dans `StandardsAgents`.
- Ne bloque pas l'exécution en cas de violation de type (mode "Warning" avec log).

---

## Signaux d’interprétation pour l’IA

- Ce composant ne doit jamais être interprété comme :
  - Un système de gestion de fichiers (il est purement informatif et validateur).

- Si une ambiguïté apparaît :
  - Se référer aux dictionnaires de la classe `StandardsAgents` pour l'autorité de vérité.

- Ne jamais supposer que :
  - Un agent peut envoyer des données sans que l'Auditor n'ait préalablement validé son format de sortie.
