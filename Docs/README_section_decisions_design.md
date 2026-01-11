## Design decisions & bonnes pratiques

Mon objectif n’était pas seulement de faire “tourner un LLM”, mais de construire une **architecture IA gouvernable**. Voici les principaux choix de design, tous visibles dans le code.

### Système fail-fast**

En architecture, le contexte dicte la décision. Là où un produit grand public (B2C) doit privilégier la haute disponibilité (dégrader le service plutôt que crasher), SecondMind privilégie l'intégrité des données.

Dans ce contexte de R&D personnelle, j'ai imposé un Fail-Fast strict : je considère qu'une "erreur silencieuse" (masquée par un fallback mou) est infiniment plus dangereuse qu'un crash explicite. Si une règle critique manque, le système doit s'arrêter, pas improviser.

### 1. Single Source of Truth (AuditorBase + config_paths)

Objectif : zéro chemin hardcodé, zéro configuration dispersée.

- `config_paths.py` définit une fois pour toutes :
  - `ROOT_DIR`, `AGENTIQUE_DIR`, `MEMOIRE_DIR`, `DATA_TRAINING_CENTER_DIR`, etc.
- `AuditorBase` fournit les chemins par **nom logique d’agent** via `get_path("...")` :
  - ex. pour la mémoire :
    - `agent_memoire` utilise `self.auditor.get_path("brute")`, `("historique")`, `("persistante")`, `("reflexive")`, etc.
  - pour les moteurs :
    - `MoteurLLM` lit `config_moteurllm.yaml` via un chemin standard défini dans `StandardsAgents.moteurllm`.
  - pour le RAG Code :
    - `AgentRechercheCode` lit `memoire/code/...` et `config_recherche_code.yaml` via `AuditorBase`.

**Impact :**

- Portabilité : pour déplacer le projet de `D:/...` à un autre environnement, je change uniquement le marqueur `.project_root`.
- Auditabilité : `AgentAuditor` et `GardienProjet` peuvent valider que tout passe bien par l’Auditor (pas de chemin sauvage).

---

### 3. Contrats d’interface stricts (contrats_interface.py)

Toutes les données inter‑agents passent par des dataclasses :

- **Intentions** : `ResultatIntention(prompt, sujet, action, categorie)`.
- **Recherche & contexte** : `ResultatRecherche(souvenirs_bruts, ...)`, `ResultatContexte(...)`.
- **Jugement** : `ResultatJuge(valide, score, raison, details)`.
- **Pipeline complet** : `StandardPrompt` contient l’intégralité du contexte avant l’appel LLM.
- **Persistance** : `Interaction` + `MetadataFichier` pour chaque entrée sauvegardée.

L’`AgentAuditor` vérifie :

- que les instanciations de ces dataclasses utilisent **uniquement** les champs définis,
- que personne ne bricole des `dict` qui “imitent” ces contrats (shadow detection).

**Résultat :**

- Toutes les jonctions sont typées (RAG, contexte, LLM, mémoire, juge).
- Pas de “données JSON magiques” qui circulent, tout est standardisé et vérifiable.

---

### 4. Architecture multi‑agents claire et indépendante

Principe : **AgentSemi est le seul qui importe les autres agents**.

- `AgentSemi` :
  - crée `AgentMemoire`, `AgentRecherche`, `AgentContexte`, `AgentParole`, `AgentJuge`, `AgentReflexor`, `IntentionDetector`, `RechercheCodeExtractor`, `RechercheCodeAdapter`, `ProcesseurBrutePersistante`, `MoteurLLM`, `MoteurMiniLLM`, `MoteurVectoriel`.
  - injecte les dépendances explicitement via les constructeurs.
- Les agents spécialisés ne s’importent pas entre eux :
  - `AgentContexte` ne fait pas `import AgentMemoire`.
  - Il reçoit `agent_recherche` / `agent_juge` comme paramètres, fournis par `AgentSemi`.

**Avantages :**

- Faible couplage : chaque agent reste concentré sur sa mission (recherche, contexte, parole, mémoire, juge, réflexif…).
- Clarté : la pipeline `penser()` est **la** carte des flux de données du système.

---

### 5. Tri‑modèle LLM (main + mini + vectoriel)

Je n’utilise pas “un LLM”, mais :

1. **Main LLM (`MoteurLLM`)** pour la génération riche :
   - Qwen / Mistral local (GGUF via llama.cpp ou Transformers/LoRA).
   - Configurable via `config_moteurllm.yaml` :
     - context window, n_gpu_layers, quantization, temperature, stop_tokens, etc.

2. **Mini LLM (`MoteurMiniLLM`)** pour les tâches rapides :
   - Phi‑3 ou modèle léger pour :
     - IntentionDetector,
     - AgentJuge,
     - petites tâches réflexives.
   - Configuré via `config_moteur_mini_llm.yaml`.

3. **Moteur vectoriel (`MoteurVectoriel`)** :
   - SentenceTransformers + FAISS pour la mémoire sémantique persistante.
   - Chaque `add_fragment(texte, meta)` sauvegarde :
     - l’embedding dans FAISS,
     - les métadonnées (incluant `contenu`) dans un JSON.

**Ce que ça montre :**

- Maîtrise de la **gestion mémoire / VRAM** (GGUF, quantization, context window).
- Capacité à séparer clairement :
  - la génération (coûteuse),
  - la classification/contrôle (rapide),
  - la mémoire vectorielle (long terme).

---

### 6. Gouvernance, audit et observabilité

Plusieurs couches travaillent ensemble :

- **GardienProjet** :
  - surveille les fichiers critiques (`agent_Semi.py`, `agent_Juge.py`, `agent_Parole.py`, `contrats_interface.py`),
  - déclenche une pensée de `AgentSemi` via une API interne (`/internal/think`),
  - synchronise périodiquement les statistiques vers le backend (`/api/stats/sync`).

- **AgentAuditor** :
  - scanne le code des agents (héritage `AgentBase`, usage de `self.logger`, obéissance aux contrats),
  - audite les flux LLM ↔ mémoire via `dashboard_stats` écrits dans les YAML,
  - génère une cartographie du projet (`mapping_structure/project_map.json`).

- **AgentReflexor** :
  - se déclenche sur le signal `!!!`,
  - cherche dans la mémoire vectorielle des cas similaires,
  - appelle le LLM pour analyser la cause racine et générer une “correction comportementale”,
  - journalise la trace réflexive dans `memoire/reflexive/journal_de_doute_reflexif.md` + FAISS + Whoosh.

- **Prompt Viewer** :
  - montre le prompt final (ChatML) que voit le LLM, en temps réel (`/api/last_prompt`).

- **Benchmark Lab** :
  - mesure précisément les performances (tokens/s, TTFT, latence inter‑token, VRAM),
  - pour le main LLM, le mini LLM, et tout le pipeline.

**Résultat :**
Mon système est instrumenté pour **se surveiller**, se corriger et s’auditer lui‑même, pas seulement pour générer du texte.

---

### 7. RAG Code intégré au cycle de vie du projet

Le RAG Code est une première classe citoyenne :

- **RechercheCodeExtractor** :
  - intercepte les réponses LLM, extrait les blocs ```code``` et produit :
    - fichiers physiques (`memoire/code/code_extraits/...`),
    - base JSONL pour FAISS (`code_chunks.jsonl`).
- **AgentRechercheCode** :
  - lit l’architecture (fichier `code_architecture.json`),
  - charge FAISS et les métadonnées liées aux chunks,
  - permet de rechercher par similarité et par graphe de dépendances (`chercher_code`).

- **RechercheCodeAdapter** :
  - fournit à `AgentSemi` un contexte compressé basé sur :
    - `modules_concernes`,
    - `context` (chunks de code),
    - `summary`.
  - `AgentSemi` transforme ce contexte en `Souvenir(type="code_source")` et l’injecte en priorité dans le prompt.

**Impact :**
Le LLM ne “devine” pas le code du projet, il lit réellement les fichiers, l’architecture et les artefacts générés.

---

### 8.Persistance atomique
Pour éviter la corruption de données (fichiers JSON tronqués) en cas d'arrêt brutal, l'AgentMemoire force l'écriture physique via flush() et os.fsync() pour chaque interaction critique.

---

En combinant ces décisions (SSOT, META_agent, contrats typés, tri‑modèle, gouvernance multi‑couches, RAG Code), j’ai construit un système IA qui est :

- **local** (pas de dépendance cloud),
- **auditabl**e (standards et logs partout),
- **composable** (multi‑agents, contrats stricts),
- **orienté produit** (interfaces Hub, IDE, Prompt Viewer, Benchmark),
- et prêt à évoluer (ajout d’agents spécialisés, nouvelles mémoires, nouveaux profils LLM).
