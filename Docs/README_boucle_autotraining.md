# 🔄 Boucle Auto-Alimentée de Training

## L'IA qui Génère ses Propres Données d'Entraînement

---

## Le Problème

Le fine-tuning d'un modèle nécessite des **données de qualité**. Les options classiques :

| Approche | Inconvénient |
|----------|--------------|
| **Annotation manuelle** | Coûteux, lent, fastidieux |
| **Données synthétiques** (GPT) | Biais, pas représentatif de l'usage réel |
| **Datasets commerciaux** | Cher, générique, pas adapté au domaine |

**Le paradoxe** : Pour améliorer mon classifieur d'intentions, j'ai besoin de données qui reflètent *mon* usage — mais ces données n'existent qu'après avoir utilisé le système.

---

## L'Insight

Et si chaque interaction **devenait automatiquement** une donnée d'entraînement potentielle ?

Le système s'utilise → génère des données → s'améliore → s'utilise mieux → génère de meilleures données...

**Une boucle vertueuse d'auto-amélioration.**

---

## La Solution

### Architecture en Deux Boucles

**Boucle 1 : Usage Normal (temps réel)**
```
User → SecondMind → Réponse
              ↓
        AgentMemoire (sauvegarde)
              ↓
        AutoDatasetBuilder (évaluation qualité)
              ↓
        Dataset JSONL (si qualifié)
```

**Boucle 2 : Entraînement (asynchrone)**
```
Dataset JSONL (seuil atteint)
              ↓
        AgentEntraineur (fusion + entraînement)
              ↓
        Nouveaux classifieurs .pth
              ↓
        IntentionDetector (modèle amélioré)
```

---

## Le Quality Gate

Toutes les interactions ne méritent pas d'être apprises. L'**AutoDatasetBuilder** applique un filtre strict :

### Critères d'Exclusion

| Critère | Raison |
|---------|--------|
| Trop court (< 10 caractères) | "ok", "oui" → pas d'intention claire |
| Trop peu de mots (< 3) | Besoin d'un contexte minimal |
| Commandes système | `!!!`, `+1`, `-1` → bruit technique |
| Classification "inconnu" | Si le modèle n'est pas sûr, on n'apprend pas son erreur |

### Critères d'Inclusion

| Critère | Raison |
|---------|--------|
| Prompt naturel | Reflète l'usage réel |
| Classification confiante | Le triplet Sujet/Action/Catégorie est clair |
| Longueur raisonnable | Assez de contexte pour SBERT |

---

## Le Pipeline de Données

### Sources Fusionnées

L'AgentEntraineur combine plusieurs sources avec dédoublonnage :

| Fichier | Source | Rôle |
|---------|--------|------|
| `intentions_base.jsonl` | Manuel | Seed initial (~50 exemples annotés) |
| `batch_dataset.jsonl` | Auto-généré | Croît avec l'usage normal |
| `live_dataset.jsonl` | Temps réel | Feedback explicite (optionnel) |

### Format des Données

Chaque ligne est un triplet d'intention :
```json
{"prompt": "Peux-tu analyser agent_Semi.py ?", "sujet": "Script", "action": "Penser", "categorie": "Agent"}
```

C'est exactement ce dont SBERT a besoin pour entraîner les 3 classifieurs.

---

## Déclenchement de l'Entraînement

L'**AgentEntraineur** peut être déclenché par :

| Trigger | Description |
|---------|-------------|
| **Seuil d'exemples** | Ex: tous les 100 nouveaux exemples |
| **Commande manuelle** | Quand je veux forcer un réentraînement |
| **Schedule** | Ex: tous les dimanches soir |

L'entraînement est **non-bloquant** — le système continue de fonctionner pendant que les nouveaux modèles sont préparés.

---

## Bénéfices

### 1. Données Représentatives
Le dataset reflète **mon usage réel**, pas des exemples théoriques ou génériques.

### 2. Amélioration Continue
Plus j'utilise SecondMind, plus il devient précis. La courbe d'apprentissage suit ma courbe d'usage.

### 3. Zéro Annotation Manuelle
Après le seed initial, je n'ai qu'à utiliser le système normalement. Le reste est automatique.

### 4. Contrôle Qualité Intégré
Le Quality Gate filtre le bruit sans intervention. Seules les interactions "propres" alimentent le modèle.

### 5. Traçabilité Complète
Chaque donnée d'entraînement est liée à une interaction réelle, horodatée, avec son contexte.

---

## Le Cercle Vertueux

```
┌─────────────────────────────────────────────┐
│                                             │
│   Usage → Données → Entraînement → Usage    │
│     ↑                                 │     │
│     └─────────── Amélioration ────────┘     │
│                                             │
└─────────────────────────────────────────────┘
```

Le système **apprend de lui-même** sans fine-tuning coûteux, sans annotation manuelle, sans données externes.

---

## Fichiers Clés

- `auto_dataset_builder.py` — Quality Gate + extraction des triplets
- `agent_Entraineur.py` — Fusion des sources + entraînement PyTorch
- `intention_detector.py` — Consommateur des modèles entraînés

---

*Maxime Gagné — Architecte Cognitif — SecondMind*
