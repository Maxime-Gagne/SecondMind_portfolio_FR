# ⚖️ Scoring de Pertinence par Couverture

## Le Juge qui Filtre le Bruit du RAG

---

## Le Problème

Les algorithmes de similarité classiques (Jaccard, Cosine) répondent à : *"Ces deux textes se ressemblent-ils ?"*

Mauvaise question pour un RAG. Un fichier de 1000 mots contenant mes 3 mots-clés obtient un score Jaccard de 3/1003 ≈ 0.003 — rejeté alors qu'il est pertinent.

---

## L'Insight : Couverture > Similarité

La bonne question : *"Quelle fraction de ma demande est couverte par ce document ?"*

| Approche | Formule | Résultat (3 mots trouvés dans 1000) |
|----------|---------|-------------------------------------|
| Jaccard | intersection / union | 0.003 ❌ |
| **Couverture (Recall)** | intersection / taille_prompt | 1.0 ✅ |

---

## La Méthode

### 1. Analyse Multi-Source
Le score final combine trois signaux :

| Signal | Logique | Poids |
|--------|---------|-------|
| **Contenu** | Mots du prompt présents dans le fichier | Base |
| **Titre** | Match sur le nom du fichier | ×1.5 (boost) |
| **Intention** | Tags Sujet/Action/Catégorie présents | +0.20 par tag |

### 2. Optimisations Linguistiques

- **Stop Words explicite** — Filtre "le", "de", "un" mais garde "IA", "DB", "UI"
- **Lemmatisation légère** — "scripts" → "script" (sans dépendance lourde)
- **Stratégie Max** — `max(score_contenu, score_titre)` évite de pénaliser les fichiers bien nommés

---

## Synergie avec le Système

```
IntentionDetector (Sujet/Action/Catégorie)
         ↓
    Nommage Sémantique (titre = intention)
         ↓
    Scoring Pertinence (boost titre + bonus intention)
```

Le titre **encode déjà l'intention** grâce au nommage sémantique. Le Juge exploite cette information pour départager les candidats.

---

## Fichiers Clés

- `agent_Juge.py` — Méthode `calculer_pertinence_semantique()`

---

*Maxime Gagné — Architecte Cognitif — SecondMind*
