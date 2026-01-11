# MetaAgent

**Type :** Système  
**Rôle principal :** Agir comme une métaclasse pour l'injection automatique de composants communs (audit, logs, stats) et l'instrumentation des méthodes d'agents.  
**Portée :** Globale  
**Statut :** Stable

---

## Description fonctionnelle

Le MetaAgent est le moteur d'infrastructure qui transforme une classe Python standard en un Agent autonome et supervisé. Il intercepte la création de l'instance pour injecter systématiquement un gestionnaire de statistiques, un auditeur de conformité, un logger cognitif et une mémoire vive (RAM). Il réalise également un "monkey patching" transparent des méthodes pour mesurer automatiquement les performances et les taux d'erreur.

---

## Objectifs

- Standardiser l'architecture interne de tous les agents du système.
- Automatiser la collecte de métriques de performance sans modifier le code métier de l'agent.
- Garantir que chaque agent possède ses propres outils de gouvernance dès son'initialisation.

---

## Non-objectifs

Ce composant ne doit pas :
- Définir le comportement intelligent ou décisionnel de l'agent.
- Gérer la communication réseau entre agents (responsabilité de l'orchestrateur).

---

## Responsabilités

Responsabilités :
- Injection ordonnée des instances `MemoireTravailRAM`, `StatsBase`, `AuditorBase` et `CognitiveLogger`.
- Auto-instrumentation des méthodes publiques pour le suivi des appels, des erreurs et du temps d'exécution (`wrapper_stats`).
- Fourniture de méthodes utilitaires communes pour le calcul de pertinence sémantique et la validation des échanges.
- Gestion du cycle de vie initial de l'agent avant l'exécution de son propre `__init__`.

Ce composant n’est pas responsable de :
- La persistance des données à long terme (rôle de l'AgentMemoire).

---

## Interfaces logiques

Expose :
- `AgentBase` : Classe de base facilitant l'application de la métaclasse.
- `_creer_wrapper_stats()` : Mécanisme interne de monitoring des méthodes.

Consomme :
- `AuditorBase` : Pour valider les échanges et enregistrer les statistiques.
- `CognitiveLogger` : Pour la journalisation des pensées et événements.
- `StatsBase` : Pour la tenue des compteurs d'exécution.

---

## Invariants

- L'injection des composants doit respecter un ordre strict : RAM → Stats → Auditor → Logger.
- Le monitoring automatique ignore systématiquement les méthodes privées (commençant par `_`).
- Le singleton `MemoireTravailRAM` est partagé entre les instances pour simuler un espace de travail commun en RAM.

---

## Dépendances conceptuelles

Dépend de :
- `functools` : Pour la préservation des signatures de méthodes lors de la décoration.
- `agentique.base.contrats_interface` : Pour les modèles de données des statistiques.

N’est jamais dépendant de :
- La logique spécifique d'un sous-agent (reste agnostique au rôle de l'agent).

---

## Contraintes connues

- L'auto-instrumentation (monkey patching) se produit au moment de l'appel de la classe, ce qui peut légèrement ralentir l'instanciation initiale.
- Toute erreur dans le `wrapper_stats` peut potentiellement masquer ou altérer les exceptions d'origine de l'agent.

---

## Signaux d’interprétation pour l’IA

- Ce composant ne doit jamais être interprété comme un agent fonctionnel ; c'est un "moule" ou un "template" d'exécution.
- En cas d'ambiguïté, se référer à la méthode `__call__` de la métaclasse pour comprendre l'état initial de l'objet.
- Ne jamais supposer que les méthodes d'un agent héritant de `AgentBase` ne sont pas surveillées ; elles le sont toutes par défaut si elles sont publiques.
