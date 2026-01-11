# 🧠 Système Mémoire AgentSemi

Documentation complète du système de mémoire persistante d'AgentSemi avec classification intelligente des types.

## 📋 Vue d'ensemble

Le système mémoire d'AgentSemi sépare intelligemment différents types d'informations pour optimiser l'apprentissage et éviter la pollution entre connaissances universelles et conversations personnelles.


## 🗂️ Types de Mémoire (8 types)
types_memoire:
  # === VOS 6 TYPES EXISTANTS (INTOUCHÉS) ===

  brute:
    description: "Données brutes (EXISTANT)"
    priorite: 0.5
    retention: "temporaire"
    dossier: "memoire/brute"

  persistante:
    description: "Informations personnelles injectées (EXISTANT)"
    priorite: 0.9
    retention: "permanente"
    dossier: "memoire/persistante"

  vectorielle:
    description: "Données vectorisées (EXISTANT)"
    priorite: 0.7
    retention: "permanente"
    dossier: "memoire/vectorielle"

  reflexive:
    description: "Corrections et feedbacks utilisateur (EXISTANT)"
    priorite: 1.0
    retention: "permanente"
    dossier: "memoire/reflexive"

  historique:
    description: "Historique des interactions récentes (EXISTANT)"
    priorite: 0.8
    retention: "temporaire"
    dossier: "memoire/historique"

  temp:
    description: "Données temporaires (EXISTANT)"
    priorite: 0.3
    retention: "session"
    dossier: "memoire/temp"

  connaissances:
    description: "Faits universels, définitions, concepts"
    priorite: 0.95
    retention: "permanente"
    dossier: "memoire/connaissances"
    format_fichier: "concept_{domaine}.yaml"
    classification_auto: true
    patterns_detection:
      - "définition"
      - "qu'est-ce que"
      - "signifie"
      - "est un"
      - "propriété"
      - "caractéristique"

  modules_formation:
    description: "Modules de formation injectés (théorie musicale, logique, etc.)"
    priorite: 0.92
    retention: "permanente"
    dossier: "memoire/modules_formation"
    format_fichier: "module_{nom}.yaml"


### Ordre de Priorité
Lors d'une requête, la recherche s'effectue dans cet ordre :
1. `reflexive` (1.0) - Corrections en premier
2. `regles` (1.0) - Règles en premier
3. `feedback` (1.0) - Corrections en premier
4. `connaissances` (0.95) - Définitions
5. `modules_formation` (0.92) - Formation
6. `persistante` (0.9) - Personnel
7. `historique` (0.8) - Conversations
8. `vectorielle` (0.7) - Sémantique
9. `brute` (0.5) - Raw data
10. `temp` (0.3) - Temporaire

### Algorithme de Pertinence
- Score basé sur intersection de mots-clés
- Seuil minimum : 0.1
- Limite : 5 items par type
- Tri par score décroissant


## 📊 Structure des Fichiers

```
C:/Users/rag_personnel/
├── memoire/
│   ├── structure_memoire.yaml          # Configuration types
│   ├── brute/                          # Raw data (.json)
│   ├── persistante/                    # Personnel (.md)
│   ├── vectorielle/                    # Embeddings (.json)
│   ├── reflexive/                      # Corrections (.md)
│   ├── historique/                     # Conversations (.jsonl)
│   ├── temp/                           # Temporaire (.json)
│   ├── connaissances/                  # Définitions (.md)
│   └── modules_formation/              # Formation (.md)
├── agentique/
│   ├── Semi/
│   │   └── agent_Semi.py               # Orchestrateur principal
│   └── sous_agents_gouvernes/
│       ├── agent_Memoire/
│       │   ├── agent_Memoire.py        # Gestionnaire mémoire
│       │   └── memoire_type_manager.py # Classification
│       ├── agent_Memofix/
│       ├── agent_Reflexor/
│       └── agent_Raisonnement.py
└── Nuclear_Formation_Datacenter/
    └── connect_backend_Semi/
        └── hub_formation_backend.py     # API Flask
```
