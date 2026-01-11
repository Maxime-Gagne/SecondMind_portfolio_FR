# RAG Mémoire — Système de Mémoire Persistante Multi-Niveaux

Gestion intelligente de 10+ types de mémoire avec recherche hybride tri-moteur et consolidation différée par LLM.

```
                    FLUX TEMPS RÉEL                         FLUX DIFFÉRÉ

    Question ──────────────────────────┐      Interaction ──────────────────┐
         │                             │           │                        │
         ▼                             │           ▼                        │
   ┌─────────────┐                     │    ┌─────────────┐                 │
   │ AgentRecherche │                  │    │ AgentMemoire │                │
   │ (Tri-Moteur)   │                  │    │ (Capture)    │                │
   └──────┬──────┘                     │    └──────┬──────┘                 │
          │                            │           │                        │
    ┌─────┴─────┬─────────┐            │           ▼                        │
    ▼           ▼         ▼            │    ┌─────────────────┐             │
Everything   Whoosh    FAISS           │    │ Processeur      │             │
(fichiers)  (full-text) (vecteurs)     │    │ BrutePersistante│             │
    └─────┬─────┴─────────┘            │    │ (LLM Résumé)    │             │
          ▼                            │    └──────┬──────────┘             │
   ┌─────────────┐                     │           │                        │
   │ AgentContexte │                   │           ▼                        │
   │ (Tri & Score) │                   │    ┌─────────────┐                 │
   └──────┬──────┘                     │    │MoteurVectoriel│               │
          │                            │    │ (FAISS)       │               │
          ▼                            │    └───────────────┘               │
   Contexte Enrichi ───────────────────┴────────────────────────────► LLM
```

## Composants

| Fichier | Rôle | Entrée → Sortie |
|---------|------|-----------------|
| `agent_Recherche.py` | Recherche tri-moteur | Query → `ResultatRecherche` |
| `agent_Contexte.py` | Tri intelligent + scoring | Recherche → `ResultatContexte` |
| `recherche_memoire.py` | Lecture guidée (focus) | Fichiers → Rapport structuré |
| `agent_Memoire.py` | Capture brute + mémorisation | Interaction → Disque |
| `traitement_brute_persistante.py` | Consolidation LLM différée | Session → Résumés vectorisés |
| `moteur_vecteur.py` | Index FAISS persistant | Texte → Embedding |

## Pourquoi pas un RAG classique ?

### 1. Recherche Tri-Moteur (3 niveaux de précision)

Un RAG classique fait une seule recherche vectorielle. SecondMind combine :

| Moteur | Vitesse | Usage |
|--------|---------|-------|
| **Everything** (es.exe) | ~10ms | Pré-filtrage par nom de fichier |
| **Whoosh** | ~50ms | Recherche full-text avec tags sémantiques |
| **FAISS** | ~100ms | Similarité vectorielle pour le sens |

**Résultat mesuré : 0.08 seconde** pour une recherche complète (tri-moteur + scoring + assemblage contexte). Précision du full-text + compréhension sémantique, sans sacrifier la vitesse.

### 2. Focus-Driven Reading (Lecture Guidée)

Le `RechercheMemoireTool` ne dumpe pas le contenu brut. Il génère un **prompt système local** pour chaque fichier :

```
### 📄 FICHIER : traitement.py
🎯 **DIRECTIVE DE LECTURE** : "Vérifier la boucle while ligne 45"

⚠️ Instructions : Analyse le code ci-dessous UNIQUEMENT
   à travers le prisme de la directive ci-dessus.
```

Le LLM sait **quoi chercher** avant même de lire. Moins de tokens gaspillés, réponses plus précises.

### 3. Mémoire Multi-Types (10+ catégories)

Chaque type de mémoire a son propre comportement :

| Type | Priorité | Contenu |
|------|----------|---------|
| `reflexive` | 🔴 Haute | Règles apprises par introspection |
| `regles` | 🔴 Haute | Directives système (truth, governance) |
| `feedback` | 🟠 Moyenne | Corrections utilisateur (+1/-1) |
| `historique` | 🟡 Session | Échanges récents (continuité) |
| `persistante` | 🟢 Long-terme | Résumés consolidés par LLM |
| `connaissances` | 🟢 Long-terme | Documentation technique |

L'`AgentContexte` trie et priorise automatiquement selon le type de requête.

### 4. Consolidation Différée par Session

Les interactions brutes ne sont pas vectorisées immédiatement. Le `ProcesseurBrutePersistante` :

1. **Regroupe** les messages par session (via session_id)
2. **Attend** un timeout (4h) pour avoir le contexte complet
3. **Envoie tout le transcript** au LLM pour analyse globale
4. **Génère des micro-résumés** cohérents entre eux
5. **Vectorise individuellement** chaque résumé

Avantage : Le LLM voit la conversation complète, pas des fragments isolés. Les résumés capturent les **intentions** et les **résolutions**, pas juste les mots.

### 5. Indexation Hybride (Whoosh + FAISS)

Chaque souvenir est indexé deux fois :

```python
# Whoosh : Tags explicites pour filtrage rapide
self.agent_recherche.update_index(
    contenu=resume,
    type_memoire="persistante",
    sujet="CODE",
    action="DEBUG",
    categorie="TECHNIQUE"
)

# FAISS : Embedding pour recherche sémantique
self.moteur_vectoriel.ajouter_fragment(resume, meta={...})
```

On peut filtrer par tags (rapide) puis affiner par similarité (précis).

## Flux de Données Complet

```
[Utilisateur tape un message]
         │
         ▼
    AgentRecherche
         │
    ┌────┴────┬──────────┐
    ▼         ▼          ▼
Everything  Whoosh     FAISS
    │         │          │
    └────┬────┴──────────┘
         │
         ▼ (Souvenirs bruts)
    AgentContexte
         │
    ┌────┼────┬────────┐
    ▼    ▼    ▼        ▼
 Règles Docs Mémoire Historique
    │    │    │        │
    └────┴────┴────────┘
         │
         ▼ (ResultatContexte trié)
       LLM
         │
         ▼
    AgentMemoire ──► Sauvegarde brute (JSONL)
         │
         ▼ (4h plus tard)
    ProcesseurBrutePersistante
         │
         ▼
    Résumés vectorisés ──► Prêts pour le prochain RAG
```

## Architecture Clé

**Séparation Lecture/Écriture** : AgentRecherche lit, AgentMemoire écrit. Pas de conflit, pas de lock.

**Validation Auditor** : Chaque sortie passe par `auditor.valider_format_sortie()` pour garantir les contrats de données.

**Hot-Reload** : L'index Whoosh et FAISS peuvent être mis à jour sans redémarrer le système.
