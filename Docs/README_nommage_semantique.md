# 🧠 Nommage Sémantique par Intention

## Du Prompt à la Mémoire Retrouvable en 80ms

---

## Le Problème

Les systèmes RAG traditionnels stockent les interactions avec des noms génériques : `interaction_001.json`, `chat_20241201.json`.

Résultat : pour retrouver "toutes les fois où j'ai débogué un agent", il faut **parser le contenu de chaque fichier**. Avec des milliers d'interactions, ça devient un goulot d'étranglement.

---

## L'Insight

Et si le **nom du fichier encodait déjà l'intention** ?

Au lieu de chercher dans le contenu, on cherche dans le filesystem — une opération quasi-instantanée.

---

## La Solution

### Classification Tri-Axe

Chaque prompt utilisateur passe par l'**IntentionDetector**, un classifieur SBERT entraîné sur mes données, qui détermine trois dimensions :

| Axe | Question | Exemples |
|-----|----------|----------|
| **Sujet** | De quoi on parle ? | SecondMind, Script, Setup, Fichier, Général |
| **Action** | Qu'est-ce qu'on fait ? | Faire, Penser, Parler, Coder, Debug |
| **Catégorie** | Dans quel contexte ? | Agent, Système, Backend, Configurer, Tester... |

### Nommage Automatique

Ces trois valeurs sont concaténées pour former le nom du fichier :

```
interaction_[sujet]_[action]_[categorie]_[timestamp].json
```

**Exemples concrets :**
- `interaction_script_debug_agent_20241201143052.json`
- `interaction_setup_faire_configurer_20241201150823.json`
- `interaction_secondmind_penser_analyser_20241201162341.json`

### Recherche Ultra-Rapide

Le nom devient un **index primaire**. Pour retrouver tous les débogages d'agents :

```
Pattern : interaction_*_debug_agent_*.json
```

Everything (en thread) résout ce pattern en **~10ms** — avant même d'interroger les index vectoriels.

---

## Performance Réelle

```
[CognitiveLogger.Recherche] INFO: Recherche Stratégique terminée en 0.08s. 10 résultats.
```

**80ms** pour une recherche complète incluant :
- Filtrage filesystem par pattern (Everything)
- Recherche full-text indexée (Whoosh)
- Recherche sémantique vectorielle (FAISS)

Le nommage sémantique permet de **pré-filtrer** avant les opérations coûteuses.

---

## Taxonomie Complète

### Sujet (5 classes)
| Valeur | Quand l'utiliser |
|--------|------------------|
| `SecondMind` | Discussion sur le système IA lui-même |
| `Setup` | Installation, matériel, configuration |
| `Script` | Code Python, YAML, fichiers techniques |
| `Fichier` | Documents non-code (.txt, .md, .pdf) |
| `Général` | Tout ce qui est hors-système |

### Action (5 classes)
| Valeur | Quand l'utiliser |
|--------|------------------|
| `Faire` | Exécuter une tâche concrète |
| `Penser` | Réfléchir, analyser, comprendre |
| `Parler` | Conversation générale |
| `Coder` | Écrire du code |
| `Debug` | Corriger un problème |

### Catégorie (14 classes)
`Agent`, `Système`, `Backend`, `Planifier`, `Tester`, `Configurer`, `Documenter`, `Analyser`, `Définir`, `Comparer`, `Demander`, `Confirmer`, `Saluer`, `Autre`

---

## Bénéfices

### 1. Recherche Sans Parsing
Le nom du fichier **est** la métadonnée. Pas besoin d'ouvrir le JSON pour filtrer.

### 2. Stratégies Contextuelles
Le RAG adapte sa stratégie selon l'intention détectée :
- `action=Debug` → Priorité aux règles de gouvernance
- `sujet=Script` → Activation du RAG Code
- `categorie=Agent` → Boost sur la documentation technique

### 3. Traçabilité Cognitive
Chaque fichier porte sa "signature d'intention" — on sait **pourquoi** il a été créé, pas juste **quand**.

### 4. Évolutivité
Ajouter une nouvelle catégorie = mettre à jour l'enum + réentraîner le classifieur. Aucune modification du pipeline de recherche.

---

## Fichiers Clés

- `intention_detector.py` — Classifieur SBERT tri-axe
- `agent_Memoire.py` — Génération du nom sémantique
- `contrats_interface.py` — Définition des enums Sujet/Action/Catégorie
- `agent_Recherche.py` — Recherche stratégique multi-index

---

*Maxime Gagné — Architecte Cognitif — SecondMind*
