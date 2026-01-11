# RAG Code — Système de Recherche Intelligente

Recherche hybride (vectorielle + symbolique) sur le code source du projet, avec expansion automatique des dépendances.

```
Question utilisateur
        │
        ▼
   ┌─────────────────┐
   │   AgentCode     │  ← API publique (fournir_contexte)
   │   Orchestrateur │
   └────────┬────────┘
            │ Recherche hybride
     ┌──────┴──────┐
     ▼             ▼
  FAISS      Graphe AST
 (vecteurs)  (dépendances)
     └──────┬──────┘
            ▼
   Contexte enrichi → LLM
```

## Composants

| Fichier | Rôle | Entrée → Sortie |
|---------|------|-----------------|
| `agent_Code.py` | Orchestrateur RAG | Question → `List[ContexteCode]` |
| `moteur_vecteur_code.py` | Indexeur (scan AST + FAISS) | Projet → Index disque |
| `code_extractor_manager.py` | Analyseur flux LLM | Réponse brute → `ArtefactCode` |

## Pourquoi pas un RAG naïf ?

Un RAG classique découpe le code par lignes ou tokens fixes, puis fait une recherche par similarité. Résultat : des chunks tronqués, sans contexte, qui forcent le LLM à deviner.

### 1. Chunks sémantiques enrichis

Chaque chunk est une **unité logique** (fonction, classe, méthode) avec ses métadonnées :

```python
ContexteCode(
    signature="def fournir_contexte(self, question: str, top_k: int = 8) -> List[Any]",
    docstring="Méthode principale : reçoit une question, retourne le contexte...",
    dependencies=["chercher_code", "_generer_squelette_partiel"],
    variables_used=["self.arch", "self.moteur_vecteur"],
    return_type="List[Any]",
    key_concepts=["rag", "contexte", "recherche"]
)
```

Le LLM reçoit tout ce qu'il faut pour comprendre **ce que fait** la fonction, **ce qu'elle appelle**, et **ce qu'elle manipule**.

### 2. Expansion par graphe de dépendances

Une recherche sur "AgentMemoire" ne retourne pas que ce module. Le système :
- Parse les imports pour trouver les dépendances sortantes
- Remonte le graphe d'appels pour les dépendances entrantes
- Expand sur N niveaux de profondeur

Résultat : le LLM voit le **contexte d'intégration**, pas un fichier isolé.

### 3. Squelette dynamique filtré

Au lieu d'injecter 50 fichiers, le système génère une vue arborescente **ciblée** :

```
📦 MODULE : agent_Memoire (agentique/agent_Memoire.py)
  └── class AgentMemoire
      └── def sauvegarder_souvenir
      └── def rechercher_souvenirs
  └── def _formater_contexte
```

Le LLM voit la structure du projet sans être noyé par le code complet.

### 4. Architecture scalable (Offsets JSONL)

- **En RAM** : Index FAISS + table d'offsets (position byte de chaque chunk)
- **Sur disque** : Chunks complets en JSONL

À la requête, seuls les chunks pertinents sont lus via `seek()`. Pas de chargement de tout l'index en mémoire.

## Séparation Lecture/Écriture

| Mode | Composant | Responsabilité |
|------|-----------|----------------|
| **Lecture** | AgentCode | Interroge l'index, assemble le contexte |
| **Écriture** | MoteurVecteurCode | Scan AST, génère chunks, construit FAISS |

Cette séparation permet un **hot-reload** : on peut reconstruire l'index en arrière-plan sans interrompre les requêtes.
