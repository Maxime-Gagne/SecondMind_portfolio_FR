# AgentAuditor

Type : Gouvernance
Responsabilité primaire : Garantir l'intégrité technique, la sécurité du code et la conformité stricte des contrats de données à travers tout le système.
Statut : Stable

---

## Rôle fonctionnel

- **Fonction principale** : Effectue des audits statiques (via AST) et dynamiques (runtime) pour policer les comportements des agents et la structure du code source.
- **Problème résolu** : Empêche la dérive des contrats d'interface, détecte les "shadow dicts" (dictionnaires imitant des objets typés) et protège les données critiques contre les opérations destructives.
- **Résultat produit** : Rapports d'audit consolidés (`audit_report.json`) et cartographie dynamique du projet (`project_map.json`) pour le RAG Code.

---

## Périmètre

L’agent :
- **Fait** :
  - Analyse syntaxique profonde (AST) pour vérifier la conformité aux Dataclasses.
  - Surveillance des opérations fichiers (`unlink`, `rmtree`) sur les répertoires sanctuarisés.
  - Audit de cohérence des flux LLM ↔ Mémoire pour détecter les pertes d'informations.
  - Scan incrémental d'encodage (UTF-8) et de standards de fichiers.

- **Ne fait jamais** :
  - Ne modifie jamais la logique métier ou le comportement décisionnel des autres agents.
  - N'autorise jamais d'actions destructives sans preuve de logique de rotation de backup.
  - Ne tente pas de réparer ou de refactoriser le code de manière autonome.

---

## Contrat logique

### Entrées attendues
- **Fichiers sources (.py)** : Pour l'analyse structurelle et de sécurité.
- **Stats d'agents (YAML)** : Pour le contrôle de la télémétrie et des flux de génération.
- **Logs de violations runtime** : Pour l'intégration des erreurs détectées en cours d'exécution.

### Sorties garanties
- **Rapport d'audit** : Synthèse JSON des alertes classées par gravité (CRITIQUE, MAJEUR, ALERTE).
- **Project Map** : Index sémantique de l'arborescence projet validé techniquement.
- **Signaux de gouvernance** : Alertes prioritaires envoyées au GardienProjet en cas d'anomalie critique.

---

## Invariants

- **Source de Vérité** : Les `contrats_interface.py` sont la référence absolue pour toute validation de données.
- **Fail-Fast** : Toute opération destructive non légitime sur un sanctuaire déclenche un signal d'arrêt immédiat.
- **Déterminisme** : L'audit de flux compare mathématiquement les appels LLM aux écritures réelles en mémoire.

---

## Dépendances conceptuelles

Dépend de :
- **contrats_interface.py** : Pour la définition officielle du vocabulaire et des structures.
- **AuditorBase** : Pour la résolution sécurisée des chemins et standards.
- **Bibliothèque ast** : Pour la déconstruction logique du code source.

N’est jamais dépendant de :
- **AgentSemi** : L'audit doit pouvoir s'exécuter de manière autonome, même si l'orchestrateur est défaillant.

---

## Modes d’échec connus

- Si **mtime/size inchangé** → alors le fichier est sauté lors du scan (Optimisation du scan incrémental).
- **Limite connue** : L'analyse structurelle profonde est actuellement limitée exclusivement au langage Python.

---

## Signaux d’interprétation pour l’IA

- Cet agent ne doit jamais être utilisé pour :
  - Justifier un contournement des règles de sécurité au profit de la performance.

- Si une action semble ambiguë :
  - Toujours privilégier la sécurité (rejet de l'action) et l'émission d'une alerte.

- Ne jamais supposer que :
  - L'absence d'alerte dynamique garantit la conformité sans une validation statique préalable.
