# 📚 LiveDocs RAG — Base de Connaissance Technique "Temps Réel"

Micro-service de RAG spécialisé pour la documentation technique (Port 5000). Permet aux agents IA locaux d'écrire du code à jour (Pydantic V2, TRL, PEFT) en contournant leur date de coupure de connaissances.

---

## 🎯 Le Problème

Les modèles de langage locaux (LLMs) comme Llama-3 ou Qwen sont excellents pour le raisonnement, mais leur connaissance des librairies Python évolue moins vite que le code lui-même.

| Aspect | Description |
|--------|-------------|
| **Symptôme** | L'IA génère du code obsolète (ex: `@validator` de Pydantic V1 au lieu de `@field_validator` de V2) |
| **Cause** | Le Knowledge Cutoff (date de fin d'entraînement) précède les dernières mises à jour majeures des frameworks |
| **Conséquence** | Hallucinations syntaxiques et code qui plante à l'exécution |

---

## 💡 La Solution : LiveDocs RAG

Au lieu de ré-entraîner le modèle (coûteux et lent), j'ai conçu un système de **mémoire externe vivante**. C'est un micro-service autonome qui surveille, scrappe, vectorise et sert la documentation officielle la plus récente.

### Architecture Micro-Service

Le système est découplé du cerveau principal (SecondMind) pour garantir la stabilité et éviter les conflits de dépendances.

```
┌─────────────────────────────────────────────────────────────────┐
│                     External World                               │
│                  PyPI / HuggingFace Docs                        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              Port 5000 - LiveDocs Service                       │
│                                                                  │
│   Scraper Automatique ──► Chunker Sémantique ──► Embedder SBERT │
│                                                       │          │
│                                                       ▼          │
│                                              ┌──────────────┐    │
│                     API Flask ◄─────────────►│ Index FAISS  │    │
│                         │                    └──────────────┘    │
└─────────────────────────┼───────────────────────────────────────┘
                          │ HTTP POST
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│              Port 3000 - Main AI Agent                          │
│                                                                  │
│                      Agent Code                                  │
│                  (Contexte à jour)                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## ⚙️ Stack Technique

| Composant | Technologie |
|-----------|-------------|
| **Moteur de Recherche Vectoriel** | FAISS (Facebook AI Similarity Search) — latence < 50ms |
| **Embeddings** | `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions, optimisé CPU/GPU local) |
| **Backend** | Flask (API REST légère) |
| **Scraping** | BeautifulSoup4 + Logique de détection de version |
| **Infrastructure** | Local (RTX 3090), tourne en parallèle du LLM principal |

---

## 🔄 Flux de Données (Data Pipeline)

### 1. Ingestion Automatisée (`doc_scraper_phase2.py`)

Le système ne se contente pas de lire des fichiers textes. Il va chercher la vérité à la source :

- Détection des packages installés via `requirements.txt`
- Scraping ciblé des documentations officielles (ex: HuggingFace TRL, Pydantic)
- **Chunking Intelligent** : Découpage par sections logiques (500 tokens) avec overlap pour préserver le contexte

### 2. Indexation Sémantique

- Chaque snippet de documentation est converti en vecteur
- **Métadonnées Riches** : Chaque vecteur contient la source exacte (URL), le nom du package et la version
- **Mise à jour incrémentale** : Seuls les packages modifiés sont ré-indexés

### 3. Interrogation (Inférence)

Lorsqu'AgentCode (sur le port 3000) détecte une intention technique (ex: "Code un SFTTrainer"), il interroge LiveDocs :

```python
# Exemple d'appel interne par l'Agent Code
response = requests.post("http://localhost:5000/api/search", json={
    "query": "SFTTrainer configuration QLoRA",
    "k": 3
})
# Résultat : Injection immédiate de la classe SFTConfig (TRL v0.8+) dans le prompt
```

---

## 🚀 Fonctionnalités Clés

| Fonctionnalité | Description |
|----------------|-------------|
| ✅ **Anti-Obsolescence** | Force le LLM à utiliser les syntaxes 2024/2025 |
| ✅ **Auto-Healing** | Si une librairie change, il suffit de relancer le script de scraping, pas besoin de toucher au LLM |
| ✅ **Performance** | Recherche découplée, n'impacte pas la VRAM du GPU dédiée à l'inférence |
| ✅ **Interface de Debug** | UI web dédiée sur `http://localhost:5000` pour vérifier ce que l'IA "sait" |

---

## 📊 Impact sur le Projet SecondMind

**Avant l'intégration de LiveDocs RAG :**
- L'agent générait du code Pydantic V1 deprecated **80% du temps** sur des structures complexes

**Après l'intégration :**
- L'agent génère du code Pydantic V2 valide (`model_validator`, `field_validator`) **95% du temps**, car il a l'exemple exact sous les yeux dans le contexte

---

## 🛠️ Installation & Démarrage

```bash
# 1. Installation des dépendances
pip install -r requirements_docs.txt

# 2. Lancement du serveur (via le launcher unifié)
START_SECONDMIND.bat
# -> Lance le serveur Doc sur le port 5000
# -> Lance le Cerveau Principal sur le port 3000
```

---

## Approche Data-Centric AI

Ce module démontre une approche **Data-Centric AI** : plutôt que de demander au modèle d'apprendre par cœur, on lui fournit les outils pour vérifier ses connaissances en temps réel.

---

*Maxime Gagné — Architecte Cognitif — SecondMind*
