
## Architecture globale de SecondMind

SecondMind est un cerveau IA multi‑agents orchestré par `AgentSemi`.
L’objectif : un système local, explicable et gouvernable, capable de combiner RAG texte + RAG code + tri‑modèle LLM (main + mini + vectoriel).

### 1. Vue d’ensemble (plan de métro)
![Architecture SecondMind](agentique/architecture.drawio.png)

```text
          ┌───────────────────────────────────────────────────┐
          │                   AgentSemi                       │
          │        (orchestrateur principal, pipeline)        │
          └───────────────────────────────────────────────────┘
                  │
                  │ penser(prompt, search_mode, historique_brut)
                  ▼
        ┌────────────────┐
        │ IntentionDetector (SBERT + Mini LLM)              │
        │ → ResultatIntention (Sujet / Action / Catégorie) │
        └────────────────┘
                  │
                  ▼
        ┌────────────────┐
        │ AgentRecherche (Whoosh + Vectoriel + Everything) │
        │ → ResultatRecherche (List[Souvenir])             │
        └────────────────┘
                  │
                  ▼
        ┌────────────────┐
        │ AgentContexte                                     │
        │ → ResultatContexte (contexte, règles, historique) │
        └────────────────┘
                  │
          +-------+------------------------+
          |                                |
          | (si question code)             |
          ▼                                |
  ┌─────────────────────┐                  |
  │ RechercheCodeAdapter│                  |
  │ + AgentRechercheCode│                  |
  │ (RAG Code + graphe) │                  |
  └─────────────────────┘                  |
          │                                |
          ▼                                |
    Contexte code (Souvenir type="code")   |
          │                                |
          +--------------------------------+
                  │
                  ▼
        ┌────────────────┐
        │ AgentParole    │
        │ → StandardPrompt → prompt ChatML final           │
        └────────────────┘
                  │
                  ▼
        ┌────────────────┐
        │ MoteurLLM      │
        │ (Qwen / Mistral local, GGUF ou Transformers)     │
        └────────────────┘
                  │
                  ▼
           Réponse texte
                  │
                  ▼
        ┌────────────────┐
        │ RechercheCodeExtractor │
        │ (extraction de code)   │
        └────────────────┘
                  │
                  ▼
        ┌────────────────┐
        │ AgentJuge      │
        │ (Mini LLM)     │
        │ → ResultatJuge │
        └────────────────┘
                  │
                  ▼
        ┌───────────────────────────────────────────────┐
        │ AgentMemoire                                  │
        │ - journaux bruts JSONL                        │
        │ - historique + persistante + reflexive        │
        │ - moteur FAISS (MoteurVectoriel)              │
        └───────────────────────────────────────────────┘
                  │
                  ▼
        ┌────────────────┐
        │ ProcesseurBrutePersistante                     │
        │ (historique → persistante + RAG + vectoriel)   │
        └────────────────┘

En parallèle :
- `AgentReflexor` analyse les signaux d’alerte (`!!!`) et crée des règles de gouvernance.
- `AgentAuditor` audite le code, les contrats d’interface et la cohérence LLM ↔ mémoire.
- `GardienProjet` surveille les fichiers critiques, déclenche `AgentSemi` et la synchronisation des stats.

```

### 2. Pipeline cognitif en 7 étapes (penser)

La méthode centrale de `AgentSemi` est `penser(...)` :

1. **Commandes système & modes forcés**
   - `+1 / -1` → feedback explicite enregistré par `AgentReflexor` (+ mise à jour Whoosh / versioning de code).
   - `-1 intention` → sauvegarde d’un cas d’intention mal classée vers `memoire/reflexive/feedback`.
   - `!!!` → déclenche la boucle réflexive (`AgentReflexor.lancer_analyse_gouvernance`) et active un protocole d’alerte dans le prompt.

2. **Choix de la source d’information (search_mode)**
   - `web` → `_recherche_web(...)` (DuckDuckGo + fallback Google), synthèse par le LLM.
   - `memory` → recherche mémoire pure, sans pipeline complet.
   - `manual_context` → slots manuels envoyés depuis l’UI, convertis en `Souvenir(type="manuel")` pour overrider le contexte normal.
   - `none` / `auto` → pipeline normal avec RAG.

3. **Détection d’intention (IntentionDetector)**
   - Retourne un `ResultatIntention(prompt, sujet, action, categorie)` utilisé partout : RAG, noms de fichiers, stats.

4. **Recherche hybride (AgentRecherche)**
   - Combine :
     - FAISS (`MoteurVectoriel`) via les métadonnées `contenu`, `fichier`, `sujet/action/categorie`,
     - Whoosh (`update_index` + requêtes `MultifieldParser`),
     - Everything (es.exe) pour retrouver instantanément fichiers de règles et README.
   - Stratégie `_definir_strategie_recherche` :
     - priorité aux règles (`reflexive/regles`),
     - puis `reflexive`, `connaissances`, `historique`, `modules_formation`, `persistante`.

5. **Construction du contexte (AgentContexte)**
   - Sélectionne les meilleurs `Souvenir` via `AgentJuge.calculer_pertinence_semantique`.
   - Ajoute :
     - `regles_actives` (règles trouvées),
     - `documentation_technique` (READMEs détectés dans le prompt),
     - `historique` de conversation (RAM + continuité depuis `memoire/historique`).
   - Si la question parle de code/fichiers, `AgentSemi` appelle `RechercheCodeAdapter` pour injecter un `Souvenir` spécial “CONTEXTE CODE LIVE”.

6. **Construction du prompt ChatML (AgentParole)**
   - Assemble un `StandardPrompt` :
     - `prompt_original`,
     - `modificateurs` (search_mode, enable_thinking),
     - `intention`,
     - `historique`,
     - `contexte_utilise`, `regles`, `documentation`.
   - Produit un prompt ChatML structuré :

     ```text
     <|im_start|>system
     [Instructions système + gouvernance]
     <|im_end|>
     <|im_start|>user
     ### DOCUMENTATION_UTILE
     ...
     ### RÈGLES
     ...
     ### CONTEXTE MÉMOIRE
     ...
     ### HISTORIQUE DE CONVERSATION
     ...
     ### QUESTION ACTUELLE
     [prompt_original]
     <|im_end|>
     <|im_start|>assistant
     ```

   - Met à jour le **Prompt Viewer** via un cache partagé (`/api/last_prompt`).

7. **Génération, jugement & mémoire**
   - `MoteurLLM.generer_stream(...)` (Qwen/Mistral local, GGUF ou Transformers).

   - `RechercheCodeExtractor.traiter_reponse_llm` :
     - extrait les blocs ```code```,
     - les remplace par un placeholder compact,
     - renvoie une liste d’artefacts à sauver (`AgentMemoire.sauvegarder_artefacts_code`).

   - `AgentJuge.evaluer_coherence_reponse(...)` (Mini LLM) produit un `ResultatJuge` (valide, score, raison, details).
     - Validation Déterministe : Contrairement à une validation binaire, l'AgentJuge émet un  score de cohérence normalisé (float 0.0 - 1.0). Le système applique un seuil de rejet strict à 0.6 : toute réponse sous ce score est bloquée, loguée comme incident, et ne parvient jamais à l'utilisateur.

   - `AgentMemoire` :
     - capture l’interaction brute en JSONL (`brute/`),
     - sérialise une `Interaction` complète (`meta` = `MetadataFichier`),
     - la sauvegarde en `historique/`,
     - met à jour FAISS + Whoosh,
     - `ProcesseurBrutePersistante` transfère ensuite vers `persistante/` et met à jour les index.

---
8. **Les limites**
    - Chaque agent dispose d'un 'Scope Négatif' explicite dans sa documentation (section Ce qu'il ne fait jamais), interdisant contractuellement les débordements de responsabilité (ex: AgentRecherche ne peut pas écrire, AgentParole ne peut pas appeler le LLM).

---

Cette vue d’ensemble montre que mon système ne se limite pas à faire “un appel LLM” :
il orchestre une **chaîne cognitive complète** avec RAG, RAG code, gouvernance, feedback, supervision, et mémoire multi‑niveaux.
