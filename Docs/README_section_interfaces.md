## Interfaces & Cockpit SecondMind

Pour exploiter pleinement l’architecture multi‑agents de SecondMind, j’ai construit un **cockpit complet** autour du noyau AgentSemi.  
Chaque interface est reliée au même backend (`interface_backend_hermes.py`) et joue un rôle précis dans le système cognitif :

- Hub d’interaction & formation (`formation_secondmind.html`)
- IDE cognitif (`semicode_ide.html`)
- Prompt Viewer (debug temps réel du prompt) (`prompt_viewer.html`)
- Lab de benchmark dual‑LLM (`benchmark_dual_llm.html`)

Cette couche produit met en valeur 5 de mes forces : architecture système, gouvernance, mémoire/RAG, observabilité et optimisation LLM.

---

### 1. Hub d’interaction & formation — `formation_secondmind.html`

**Rôle :** interface principale utilisateur, pensée pour la pédagogie et l’expérimentation.

- **Chat connecté au pipeline cognitif complet**  
  - Envoi sur `/command` avec :
    - `prompt` (question utilisateur),
    - `search_mode` (auto / web / memory / manual_context),
    - `manual_context` (contenu des slots activés).
  - Côté backend, `AgentSemi.penser(...)` orchestre :
    - IntentionDetector → `ResultatIntention`
    - `AgentRecherche.recherche_hybride(...)` → `ResultatRecherche`
    - `AgentContexte.recuperer_contexte_intelligent(...)` → `ResultatContexte`
    - `AgentParole.construire_prompt_llm(...)` → prompt ChatML
    - `MoteurLLM.generer_stream(...)` → génération streamée.

- **Feedback live pour le renforcement**  
  - Champ “Feedback pour Renforcement” → `/memoire` avec `{ "feedback": "..." }`.
  - Le backend :
    - Classifie le feedback via `IntentionDetector`.
    - Sauvegarde en `memoire/reflexive/feedback/...` via `AgentMemoire.sauvegarder_memoire(...)`.
    - Option spéciale `+1` : validation de la dernière version de code via `VersionTracker` et `dernier_code_hash`.

- **Contexte manuel pilotable par l’utilisateur**  
  - 5 slots avec estimation de tokens, switch ON/OFF, sauvegarde locale.
  - Le frontend concatène les slots actifs dans `manual_context` et les envoie à `/command`.
  - Côté `AgentSemi`, si `historique_brut` est une liste de slots structurés, il peut :
    - remplacer le contexte RAG standard par une liste de `Souvenir(type="manuel")`,
    - forcer donc le LLM à ne considérer que ce que l’utilisateur a injecté.

**Ce que ça démontre :**

- Capacité à concevoir une UI qui expose **les leviers internes du moteur** (search mode, contexte) sans casser l’architecture.
- Gouvernance des feedbacks : ceux‑ci deviennent des artefacts traçables en mémoire réflexive, utilisables ensuite par le RAG et le Reflexor.

---

### 2. Prompt Viewer — `prompt_viewer.html`

**Rôle :** outil de debug pour voir **exactement** ce qui est envoyé au LLM (prompt complet, format ChatML).

- **Mécanisme côté backend :**
  - `interface_backend_hermes.py` maintient un cache partagé :
    - `prompt_viewer_cache = {"raw_prompt": "...", "timestamp": ...}` protégé par un `Lock`.
  - `AgentSemi` injecte dans `AgentParole` un callback :

    ```python
    def update_viewer_callback(prompt_str):
        cache = self.get_cache()
        lock = self.get_lock()
        with lock:
            cache["raw_prompt"] = full_raw_prompt
            cache["timestamp"] = datetime.now().isoformat()
        if self.socketio:
            self.socketio.emit('refresh_prompt_viewer', {...})
    self.agent_parole._prompt_callback = update_viewer_callback
    ```

  - `AgentParole.construire_prompt_llm(...)` appelle `_update_viewer`, qui met à jour le cache et déclenche le callback.

- **Mécanisme côté frontend :**
  - `prompt_viewer.html` interroge `/api/last_prompt` toutes les secondes.
  - Affiche :
    - `raw_prompt` (le prompt complet, tel qu’envoyé à `MoteurLLM`),
    - le timestamp,
    - la taille en caractères,
    - les balises ChatML colorisées (`<|im_start|>`, `<|im_end|>`, `<s>`, `</s>`).

**Ce que ça démontre :**

- Culture de l’**observabilité** : tu exposes le prompt final, pas un “résumé” côté front.
- Alignement avec tes contrats d’interface : ce qui est vu dans le Viewer est le résultat réel de `StandardPrompt` → `AgentParole`, pas un hack.

---

### 3. SemiCode IDE — `semicode_ide.html`

**Rôle :** environnement de développement intégré, relié au cerveau de SecondMind pour l’assistance au code.

- **Explorateur de projet & édition :**
  - `/api/list_files` : parcourt `AGENTIQUE_DIR`, `MEMOIRE_DIR` (définis dans `config_paths.py`) pour générer l’arbre.
  - `/api/read_file` / `/api/save_file` : lecture / écriture sous `ROOT_DIR`, avec :
    - contrôle de périmètre (pas d’escape path),
    - backup automatique en `/backups/YYYYMMDD/`,
    - déclenchement de `code_extractor.analyser_fichier(...)` pour enrichir la base RAG Code.

- **Exécution de code :**
  - `/api/execute_code` : exécute le script en fichier temporaire sous `ROOT_DIR/temp`, avec timeout 10s, puis affiche stdout/stderr dans un terminal intégré.

- **Chat “Semi Assistant – Mode IDE” :**
  - Le message utilisateur est enrichi avec le contexte du code :
    - si du code est sélectionné dans l’éditeur → inclusion dans un bloc ```python ... ``` dans le prompt,
    - sinon, si on parle de “ce code / ce fichier” → injection du contenu complet du fichier courant.
  - Envoi sur `/command` avec ce prompt enrichi.
  - Réponse streamée :
    - détection des blocs de code ```lang\n...\n``` via regex,
    - boutons “Appliquer” (remplace le contenu de l’éditeur) et “Copier”.

- **Validation (+1) intégrée :**
  - Bouton ✓ envoie un `prompt: "+1"` sur `/command`.
  - Côté `AgentSemi._gerer_commandes_systeme`, ce signal :
    - enregistre un feedback détaillé via `AgentReflexor.enregistrer_feedback_etendu(...)`,
    - si `dernier_code_hash` est présent, marque la version comme validée dans `VersionTracker`.

**Ce que ça démontre :**

- Capacité à **intégrer le moteur cognitif dans un flux de dev réel** (lecture/sauvegarde de fichiers, exécution, refactoring).
- Exploitation complète de ton RAG Code (Extractor + AgentRechercheCode + Adapter) pour donner à Semi une vue structurée du projet.

---

### 4. Dual LLM Benchmark Lab — `benchmark_dual_llm.html`

**Rôle :** banc de test visuel pour ton architecture tri‑modèle (Main LLM 14B, Mini LLM, pipeline complet).

- **Config & découverte des modèles :**
  - `/api/config_benchmark` lit via `AuditorBase` :
    - la config du `MoteurLLM` (`config_moteurllm.yaml`),
    - celle du `MoteurMiniLLM` (`config_moteur_mini_llm.yaml`),
  - et renvoie au front : modèle, fenêtre de contexte, couches GPU, etc.

- **Benchmarks dédiés :**
  - `/api/benchmark/main_llm` :
    - utilise `agent_semi.moteur_llm.generer_stream(prompt)` pour un vrai prompt.
    - mesure :
      - temps total,
      - TTFT (time to first token),
      - latence inter‑token moyenne,
      - tokens/s,
      - VRAM utilisée (via NVML),
      - nombre de tokens générés.
  - `/api/benchmark/mini_llm` :
    - même logique pour `MoteurMiniLLM` (stream si disponible, sinon fallback non‑stream).
  - `/api/benchmark/full_pipeline` :
    - chronomètre :
      - classification (IntentionDetector),
      - RAG + préparation (latence avant le 1er token),
      - génération pure,
      - total time,
      - tokens/s sur la génération,
      - VRAM totale,
      - intention détectée.

- **Interface graphique :**
  - Deux panneaux pour chaque LLM (main / mini) :
    - tokens/s, VRAM, latence, temps total,
    - graphes Chart.js de performance dans le temps.
  - Un panneau pipeline complet (classification_time, rag_latency, generation_time, total_time, tokens/s).
  - Un tableau historique des runs (type de test, perf, VRAM, durée, classification).

**Ce que ça démontre :**

- Maîtrise fine de l’**ingénierie LLM** (performance, latence, VRAM), au‑delà du simple “appel d’API”.
- Capacité à outiller l’architecture tri‑modèle et à la rendre **mesurable** et **optimisable**.

---

### 5. Backend orchestral unique — `interface_backend_hermes.py`

Toutes ces interfaces reposent sur un backend central, cohérent avec tes règles de gouvernance :

- **Orchestration :**
  - Initialise `AgentSemi` avec :
    - `socketio` (événements temps réel),
    - les callbacks Prompt Viewer (`get_cache`, `get_lock`),
    - `GardienProjet` (surveillance de fichiers critiques + sync de stats via `/api/stats/sync`).
  - Injecte `AgentSemi` dans les routes externes (routes outils, audio Whisper, etc.).

- **Routes structurées par rôle :**
  - `/command` : chemin principal pour le brain (stream direct des tokens du LLM).
  - `/memoire` : injection de mémoire (`memoire`) + feedback (`feedback`), avec classification et routage vers les bons dossiers mémoire.
  - `/transcribe` : audio → texte via Whisper (optionnel).
  - `/api/last_prompt` : exposer le cache Prompt Viewer.
  - `/api/*` : stats, audit, benchmark, historique de discussions, conversations, IDE (list_files, read_file, save_file, execute_code), liste des HTML, etc.
  - `/<filename>` : serveur générique de fichiers HTML depuis `Nuclear_Formation_Datacenter` (Hub, Formation, IDE, Benchmark, Archive, etc.).

- **Respect strict des standards :**
  - Tous les chemins passent par `AuditorBase` + `config_paths.py` (ROOT_DIR, MEMOIRE_DIR, etc.).
  - Les structures transmises restent alignées avec `contrats_interface.py` (Enums + dataclasses).
  - Les agents spécialisés ne s’importent pas entre eux : c’est toujours `AgentSemi` qui instancie et injecte.

---

### En résumé

Ce cockpit montre que je sais :

- **Industrialiser un moteur IA multi‑agents** en un environnement complet : hub, IDE, labo de bench, outils de debug.
- Exposer des **leviers de haut niveau** (feedback, modes de recherche, contexte manuel) tout en respectant mes propres règles de gouvernance (SSOT, contrats typés, séparation des rôles).
- Concevoir des outils pour moi‑même en tant que développeur / architecte (Prompt Viewer, SemiCode IDE, Benchmark Lab), ce qui accélère le debug, l’observation et l’itération sur l’architecture cognitive.
