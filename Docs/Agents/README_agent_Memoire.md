# AgentMemoire

Type : Exécutif / Gouvernance
Responsabilité primaire : Gérer de manière autonome le cycle de vie de la mémoire persistante en assurant la capture, le stockage et l'indexation de toutes les données du système.
Statut : Stable

---

## Rôle fonctionnel

- Fonction principale : Orchestre l'écriture physique des données (interactions, code, réflexions) sur le disque et coordonne leur indexation vectorielle et textuelle.
- Problème résolu : Prévient la perte d'informations critiques et permet au système de maintenir une continuité cognitive sur le long terme.
- Résultat produit : Stockage structuré (JSON/JSONL/Markdown) prêt à être consommé par les moteurs de recherche et les processeurs de consolidation.

---

## Périmètre

L’agent :
- Fait :
  - Sauvegarde "Brute" : Capture immédiate des interactions en mode Append (journalisation de sécurité).
  - Sauvegarde "Historique" : Archivage des échanges structurés (Dataclass Interaction) pour le RAG.
  - Archivage de Code : Extraction et stockage des artefacts de code (ArtefactCode) générés ou analysés.
  - Journalisation Réflexive : Maintien du "journal de doute" au format Markdown pour l'auto-amélioration.
  - Indexation : Déclenche la mise à jour des index vectoriels (FAISS) et textuels (Whoosh) après chaque écriture.

- Ne fait jamais :
  - Ne supprime de données sans une directive explicite de gouvernance.
  - Ne modifie les fichiers de configuration ou le code source du projet (uniquement les extraits et artefacts).

---

## Contrat logique

### Entrées attendues
- Interaction (Dataclass) : L'objet complet représentant un échange prompt/réponse.
- ArtefactCode (Dataclass) : Snippets de code avec leur analyse AST associée.
- Trace Réflexive (str) : Contenu Markdown décrivant un raisonnement ou une erreur.

### Sorties garanties
- Booléen de succès : Confirmation de l'écriture sécurisée et de la synchronisation disque.
- Index à jour : Disponibilité immédiate de l'information pour les recherches ultérieures.

---

## Invariants

- Atomicité : Toute sauvegarde brute utilise `flush()` et `fsync()` pour garantir l'intégrité physique sur le disque.
- Validation : Toute structure de données complexe est soumise à `auditor.valider_format_sortie` avant l'écriture.
- Dédoublonnage technique : Les "Tool Calls" (appels d'outils système) sont filtrés et exclus de l'archivage du code projet.

---

## Dépendances conceptuelles

Dépend de :
- Auditor : Pour la résolution des chemins (paths) et la validation des contrats de données.
- MoteurVectoriel : Pour la transformation des textes en fragments sémantiques.
- AgentRecherche : Pour la mise à jour de l'index textuel (Whoosh).

N’est jamais dépendant de :
- AgentParole : Il n'interagit jamais directement avec l'utilisateur final.

---

## Modes d’échec connus

- Si le dossier cible est inaccessible ou protégé en écriture → alors l'agent logue une erreur fatale et retourne False.
- Si le moteur vectoriel est absent ou échoue → alors l'agent assure tout de même l'écriture physique sur le disque (mode dégradé).

---

## Signaux d’interprétation pour l’IA

- Cet agent ne doit jamais être utilisé pour :
  - Stocker des données temporaires ou volatiles (utiliser la RAM).

- Si une action semble ambiguë :
  - Toujours privilégier la sauvegarde brute (Backup) avant tout autre traitement de mémorisation active.

- Ne jamais supposer que :
  - Une donnée est mémorisée si le `fsync` n'a pas été confirmé par le système de fichiers.
