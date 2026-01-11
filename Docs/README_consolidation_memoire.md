# 🧠 Consolidation Mémoire par Session

## Du Chaos Granulaire à la Mémoire Cohérente

### Architecture en Deux Temps

**Temps 1 : Accumulation (temps réel)**
```
User → SecondMind → Réponse
              ↓
        AgentMemoire
              ↓
        historique/interaction_xxx.json (granulaire)
```

**Temps 2 : Consolidation (différé, après 4h d'inactivité)**
```
historique/*.json (session complète)
              ↓
        ProcesseurBrutePersistante
              ↓
        LLM analyse TOUT le transcript
              ↓
        Classification cohérente par message
              ↓
        persistante/*.json (résumés indexés)
```

### Le Flow Détaillé

| Étape | Action |
|-------|--------|
| 1 | Grouper les fichiers par `session_id` |
| 2 | Attendre time-out (4h sans activité) |
| 3 | Construire le transcript complet |
| 4 | Envoyer au LLM avec consigne de cohérence |
| 5 | Parser la réponse bloc par bloc |
| 6 | Sauvegarder 1 fichier JSON par message (résumé + intention) |
| 7 | Vectoriser chaque résumé individuellement |
| 8 | Marquer les fichiers source comme traités |

---

## La Consigne LLM (Extrait)

> **OBJECTIF CRITIQUE : MAINTIEN DE L'INTENTION**
>
> Analyse le contexte global pour déterminer le SUJET RÉEL de la session.
>
> Exemple : Si l'utilisateur dit "Bonjour" puis "Corrige ce script python", le "Bonjour" doit être classé SCRIPT/CODER (car c'est le but de la session), pas GENERAL/PARLER.

Le LLM voit **l'intention de la session**, pas juste le message isolé.

---

## Synergie avec le Système

```
Consolidation génère des résumés classifiés
              ↓
        AutoDatasetBuilder (alimentation training)
              ↓
        IntentionDetector (amélioration continue)
```

Les résumés consolidés alimentent automatiquement le dataset d'entraînement — la boucle d'auto-amélioration continue.

---

## Sécurités Intégrées

| Mécanisme | Protection |
|-----------|------------|
| **Time-out 4h** | Ne consolide pas une session en cours |
| **État persistant** | Fichiers traités marqués, pas de double-traitement |
| **Stop Signal** | Le LLM s'arrête à `=== FIN DE SESSION ===` |
| **Fichiers sources préservés** | `historique/` reste intact, `persistante/` est la consolidation |

---

## Bénéfices

### 1. Cohérence d'Intention
Un "Bonjour" dans une session de debug est classé DEBUG, pas PARLER.

### 2. Résumés Exploitables
Le RAG cherche dans des résumés denses, pas dans des échanges verbeux.

### 3. Alimentation Training
Chaque session consolidée génère des données d'entraînement de qualité.

### 4. Traçabilité
Lien préservé entre résumé (`persistante/`) et source (`historique/`).

---

## Fichiers Clés

- `traitement_brute_persistante.py` — Processeur de consolidation
- `agent_Memoire.py` — Sauvegarde initiale dans `historique/`
- `auto_dataset_builder.py` — Alimentation du training

---

*Maxime Gagné — Architecte Cognitif — SecondMind*
