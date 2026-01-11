### AgentAuditor – Gardien de la gouvernance technique et analyse statique

J’ai conçu `AgentAuditor` comme un **agent de gouvernance** dédié à la qualité et à la sécurité de l’architecture multi‑agents. Il s’appuie sur les contrats d’interface et sur l’`AuditorBase` (source de vérité des chemins et configs) pour surveiller en continu le code et les flux de données.

**Rôle global**

- Garantir la **conformité aux contrats d’interface** (`contrats_interface.py`).
- Protéger la **mémoire** et les dossiers critiques (`memoire/brute`, `persistante`, `reflexive`…) contre les opérations destructives non légitimes.
- Vérifier la **structure des agents** (héritage `AgentBase`, usage du logger, respect de META_agent).
- Auditer la **cohérence des flux** entre le LLM et la mémoire (pas de perte d’interactions).
- Produire une **cartographie JSON** des fichiers Python pour le RAG Code et la compréhension globale du projet.

---

#### 1. Audit Data & Sécurité

`AgentAuditor` s’appuie sur l’AST Python pour analyser le code source sans l’exécuter :

- **ContractComplianceVisitor**  
  Vérifie que toutes les instanciations de dataclasses utilisent **uniquement** les champs définis dans `contrats_interface.py`.  
  → Empêche l’apparition de champs fantômes comme `ResultatIntention(foo="…")`.

- **ShadowComplianceVisitor**  
  Détecte les **dictionnaires qui imitent des dataclasses** (mêmes clés que `Interaction`, `ResultatIntention`, `StandardPrompt`, etc.).  
  → Force le code à passer par les contrats d’interface officiels plutôt que par des `dict` bricolés.

- **FunctionHygieneVisitor**  
  Analyse les fonctions pour repérer les **variables mortes** (assignées mais jamais utilisées) afin de garder un code lisible et maintenable.

- **Audit sécurité fichier**  
  Scanne les fichiers pour détecter :
  - l’usage d’opérations destructives (`.unlink`, `.remove`, `rmtree`) sur des **sanctuaires** (dossiers critiques définis en YAML),
  - des **patterns interdits** (eval brut, accès non contrôlé, etc.).  
  Les exceptions légitimes de rotation de backups sont reconnues (présence de `shutil.copy`, `backup`, `rotation`…), afin de ne pas bloquer les mécanismes de sauvegarde.

---

#### 2. Audit Structure & Architecture

Côté structure, `AgentAuditor` vérifie que les agents restent conformes à tes standards META_agent :

- `auditer_conformite_structurelle` :
  - s’assure que tout fichier `agent_*.py` contient au moins une classe qui **hérite de `AgentBase`**,  
  - vérifie la présence de `self.logger` pour garantir l’usage du **CognitiveLogger** injecté par la métaclasse.

- `generer_cartographie` :
  - lit la configuration YAML de l’auditor (périmètre, exclusions),
  - parcourt uniquement les dossiers autorisés (par défaut `agentique/`),
  - génère un `project_map.json` listant tous les fichiers Python valides (chemins relatifs).  
  Cette cartographie sert de base au **RAG Code** (`AgentRechercheCode`) et aux vues d’architecture (SemiCode IDE, outils de debug).

---

#### 3. Audit des Flux & Supervision LLM ↔ Mémoire

`AgentAuditor` ne se limite pas au code : il supervise aussi la cohérence des flux de données.

- `_charger_stats_agent` lit, via `AuditorBase`, la section `dashboard_stats` des YAML de chaque agent (mise à jour périodique par `SynchroniseurStats` dans le backend).
- `auditer_coherence_flux` compare :
  - le nombre d’appels au **Moteur LLM** (`appels_generer` + `appels_generer_stream`),
  - au nombre de sauvegardes en **mémoire brute** (`appels_sauvegarder_interaction_brute`),
  - et au nombre d’entrées en **historique** (`appels_memoriser_interaction`).

S’il détecte que :

- le LLM a généré plus de fois que la mémoire brute n’a journalisé, il remonte une **alerte de fuite de données** au Gardien (`_signaler_au_gardien`),
- l’historique contient plus d’entrées que la brute, il signale une **anomalie logique** (création ex‑nihilo).

Cette couche garantit qu’aucune réponse du LLM ne peut disparaître silencieusement du pipeline de persistance.

---

#### 4. Orchestration globale : `auditer_systeme()`

L’entrée principale `auditer_systeme(mode="sanity_check" | "deep_scan")` :

1. lit son périmètre et ses exclusions depuis `config_agent_auditor.yaml`,
2. parcourt les fichiers ciblés,
3. applique, pour chaque fichier :
   - l’audit sécurité,
   - la conformité structurelle,
   - l’hygiène interne,
   - la conformité aux contrats,
   - la détection de shadow dicts (en mode `deep_scan`),
4. exécute un audit global des flux LLM ↔ mémoire,
5. régénère la cartographie de projet,
6. écrit un rapport JSON complet dans `agentique/sous_agents_gouvernes/agent_Auditor/logs/audit_report.json`.

Ce rapport est utilisé par le **GardienProjet** pour automatiser les revues après modification de fichiers critiques (`agent_Semi.py`, `contrats_interface.py`, etc.).

---

**Impact dans l’architecture**

Avec `AgentAuditor`, j’ai industrialisé la gouvernance de mon système multi‑agents :

- aucune dérive de chemin ou de contrat d’interface n’est tolérée (source unique de vérité via `AuditorBase` + `contrats_interface`),
- les agents restent structurellement alignés sur **META_agent**,
- les flux LLM → mémoire sont supervisés globalement (pas de trous dans la journalisation),
- la structure du projet est constamment cartographiée pour alimenter le **RAG Code** et mes outils (SemiCode IDE, Prompt Viewer).

En pratique, `AgentAuditor` joue le rôle d’**auditeur interne automatique** : il vérifie que le cerveau (AgentSemi) et ses sous‑agents respectent en permanence les règles d’architecture que j’ai définies.