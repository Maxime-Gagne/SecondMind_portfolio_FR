# StatsManager

Type : Système / Infrastructure
Rôle principal : Assurer la télémétrie autonome et la persistance des métriques d'exécution pour chaque agent du système.
Portée : Transversale
Statut : Stable

---

## Description fonctionnelle

Le StatsManager est un module transversal qui comptabilise automatiquement les appels de méthodes, les erreurs et les métriques métier pour l'ensemble des agents SecondMind. Il fonctionne sans intervention manuelle dans le code métier grâce à un mécanisme d'interception par métaclasse. Les données récoltées sont persistées dans les fichiers YAML de configuration pour permettre un audit de flux et une visualisation via dashboard.

---

## Objectifs

- Collecter en temps réel les statistiques d'utilisation (appels, erreurs, succès) de chaque agent.
- Automatiser la mesure de performance (latence) des méthodes publiques.
- Centraliser les métriques pour faciliter la supervision et l'audit logique par l'AgentAuditor.

---

## Non-objectifs

Ce composant :
- N’a pas pour but de :
  - Juger la qualité sémantique ou la pertinence métier des résultats (compte les succès techniques uniquement).
  - Bloquer l'exécution d'un agent en cas de dépassement de seuil (rôle de supervision passif).

---

## Responsabilités

Ce composant est responsable de :
- Intercepter chaque appel de méthode publique via la métaclasse `MetaAgent`.
- Incrémenter les compteurs globaux et spécifiques en mémoire vive (RAM).
- Gérer la synchronisation périodique des données vers les fichiers physiques via le backend.
- Créer des backups de sécurité des fichiers de configuration avant toute injection de statistiques.

Ce composant n’est jamais responsable de :
- La correction automatique des erreurs détectées lors des appels de méthodes.
- Les statistiques mesurent la stabilité technique, pas la validité sémantique.

---

## Interfaces logiques

Expose :
- `incrementer_appel()` : Incrémente le compteur global de l'agent source.
- `incrementer_stat_specifique(nom_methode)` : Crée ou incrémente une clé dynamique pour une fonction précise.
- `obtenir_statistiques()` : Fournit la structure complète des données pour l'export ou l'audit.

Consomme :
- `MetaAgent` : Fournit le moteur d'instrumentation nécessaire à l'interception.
- `interface_backend_hermes.py` : Utilise le `SynchroniseurStats` pour la persistance disque.

---

## Invariants

- L'impact CPU de l'interception doit rester négligeable car les calculs primaires s'effectuent en RAM.
- Toute persistance disque doit être précédée de la création d'un fichier de backup dans le dossier de monitoring.

---

## Dépendances conceptuelles

Dépend de :
- `StatsBase` (contrats_interface.py) : Définit la structure de données des compteurs.
- `GardienProjet` : Déclenche le signal de synchronisation périodique via l'API.

N’est jamais dépendant de :
- La logique métier spécifique d'un agent : il traite toutes les méthodes publiques de manière agnostique.

---

## Contraintes connues

- **Nomenclature critique** : Le mapping entre les classes d'agents et les fichiers YAML est défini de manière rigide dans le backend.
- **Limitation technique** : Une fonction retournant un résultat métier incorrect mais sans exception est comptabilisée comme un succès.

---

## Signaux d’interprétation pour l’IA

- Ce composant ne doit jamais être interprété comme :
  - Un système d'analyse de logs textuels (il traite des compteurs numériques).

- Si une ambiguïté apparaît :
  - Prioriser les données de `StatsBase` en RAM comme source de vérité immédiate avant la synchronisation disque.

- Ne jamais supposer que :
  - Le système peut suivre les appels de méthodes privées (commençant par `_`).
