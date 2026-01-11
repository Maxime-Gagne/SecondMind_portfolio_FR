# AgentCode

Type : Exécutif
Responsabilité primaire : Orchestrer l'accès à l'intelligence du code source via un système hybride de recherche et d'indexation.
Statut : Stable

---

## Rôle fonctionnel

- Fonction principale : Gère la lecture et l'interprétation du code via un RAG (Retrieval-Augmented Generation) combinant vecteurs et graphes de dépendances.
- Problème résolu : Permet au système de comprendre une base de code complexe, de trouver des fonctions spécifiques et de consulter la documentation technique à jour.
- Résultat produit : Fournit des objets de contexte (ContexteCode) et des squelettes dynamiques de modules pour enrichir la réflexion des autres agents.

---

## Périmètre

L’agent :
- Fait :
  - Recherche vectorielle via FAISS pour trouver des snippets de code pertinents.
  - Génération de squelettes de code ciblés montrant les signatures de classes et méthodes.
  - Expansion des recherches en suivant le graphe des dépendances des modules.
  - Interrogation d'un serveur de documentation externe pour les bibliothèques tierces (Pydantic, Transformers, etc.).
  - Déclenchement du rafraîchissement de l'index après modification des fichiers.

- Ne fait jamais :
  - N'exécute de tests unitaires ou de code en temps réel.
  - Ne modifie les fichiers sources directement (rôle de l'indexeur/moteur).

---

## Contrat logique

### Entrées attendues
- Question (str) : Requête en langage naturel ou technique sur le code.
- Index FAISS et Métadonnées : Pour la recherche vectorielle.
- Architecture JSON : Représentation structurelle du système.

### Sorties garanties
- ContexteCode (Dataclass) : Objets contenant le code, sa signature et ses dépendances.
- Souvenir (Dataclass) : Utilisé pour injecter le squelette dynamique ou la documentation externe.

---

## Invariants

- Toute sortie doit être soumise à `auditor.valider_format_sortie` avant d'être retournée.
- La recherche doit prioriser la précision via un filtrage des modules concernés avant l'expansion.
- En cas d'échec total de recherche, l'agent doit lever une erreur explicite plutôt que de renvoyer un contexte vide silencieux.

---

## Dépendances conceptuelles

Dépend de :
- MoteurVecteurCode : Pour les opérations lourdes d'indexation sur disque.
- CodeExtractorManager : Pour le parsing et l'extraction des structures de code.
- Serveur de Documentation (Port 5000) : Pour les informations techniques externes.

N’est jamais dépendant de :
- Logique de déploiement (CI/CD) : Son rôle s'arrête à la fourniture de contexte intellectuel.

---

## Modes d’échec connus

- Si l'index FAISS n'est pas chargé → alors une erreur `RuntimeError` est levée lors de la recherche.
- Limite connue : La recherche symbolique par mots-clés est limitée aux termes de plus de 3 caractères.

---

## Signaux d’interprétation pour l’IA

- Cet agent ne doit jamais être utilisé pour :
  - Deviner une structure de code sans interroger l'index.

- Si une action semble ambiguë :
  - Toujours inclure le "Squelette Dynamique" pour donner une vue d'ensemble du module trouvé.

- Ne jamais supposer que :
  - L'index est à jour si des modifications de fichiers ont eu lieu sans appel à `rafraichir_index`.
