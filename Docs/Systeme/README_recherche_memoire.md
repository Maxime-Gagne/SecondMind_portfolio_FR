# RechercheMemoireTool

Type : Système
Rôle principal : Agir comme une interface de lecture physique et un gestionnaire de résultats pour les recherches effectuées sur le disque et dans la mémoire du système.
Portée : Locale
Statut : Stable

---

## Description fonctionnelle

Le RechercheMemoireTool est un composant d'infrastructure qui transforme les demandes de haut niveau des agents (comme Semi) en opérations concrètes de lecture de fichiers ou d'interrogation de bases de données (Whoosh, vectoriel). Il assure le formatage neutre et structuré des données brutes extraites du système pour qu'elles soient directement exploitables par le moteur de réflexion.

---

## Objectifs

- Fournir une méthode unifiée pour lire des fichiers physiques, des citations exactes ou des concepts flous.
- Garantir la sécurité et l'intégrité de la lecture en validant l'existence et le type des fichiers avant accès.
- Centraliser la vision structurelle du projet en exposant la cartographie générée par l'audit.

---

## Non-objectifs

Ce composant :
- N’a pas pour but de :
  - Effectuer lui-même l'indexation vectorielle ou textuelle (délégué à l'AgentRecherche).
  - Modifier le contenu des fichiers sur le disque (lecture seule).
  - Gérer la persistance à long terme des interactions.

---

## Responsabilités

Ce composant est responsable de :
- Mapper les types de recherche ("code", "verbatim", "concept", "readme") vers les fonctions spécialisées de l'AgentRecherche.
- Découper intelligemment les requêtes multiples pour extraire des noms de fichiers uniques.
- Lire le contenu brut des fichiers et le formater en blocs de code Markdown avec détection d'extension.
- Charger et présenter la `project_map.json` pour offrir une vision stratégique de l'arborescence.

Ce composant n’est jamais responsable de :
- La décision logique sur quel fichier lire (rôle dévolu au LLM via les outils).

---

## Interfaces logiques

Expose :
- `executer(type_recherche, query)` : Routeur principal pour les différentes méthodes de récupération.
- `traiter_recherche_memoire(arguments)` : Gère les demandes de lecture multi-fichiers.
- `lire_fichier_complet(nom_fichier)` : Méthode de bas niveau pour extraire le texte structuré d'un fichier.

Consomme :
- `AgentRecherche` : Pour localiser physiquement les fichiers et interroger les index Whoosh/Vecteurs.
- `ROOT_DIR` : Pour la résolution sécurisée des chemins absolus.

---

## Invariants

- Les résultats retournés pour la lecture de fichiers doivent toujours être encapsulés dans des objets `Souvenir`.
- Aucun accès ne doit être autorisé en dehors de la racine du projet (`ROOT_DIR`).
- La sortie doit rester neutre (données brutes) pour ne pas biaiser le raisonnement de l'agent.

---

## Dépendances conceptuelles

Dépend de :
- `Pathlib` : Pour la manipulation robuste et sécurisée des chemins de fichiers.
- `contrats_interface.Souvenir` : Pour la standardisation des objets de sortie.

N’est jamais dépendant de :
- `Flask` ou l'interface UI : il fonctionne exclusivement dans la couche de service logique.

---

## Contraintes connues

- La lecture de fichiers est limitée par les permissions du système d'exploitation sur le répertoire racine.
- La localisation physique dépend de la fraîcheur de l'index de l'AgentRecherche.

---

## Signaux d’interprétation pour l’IA

- Ce composant ne doit jamais être interprété comme :
  - Un moteur de recherche internet (il ne fouille que le projet local et sa mémoire).

- Si une ambiguïté apparaît :
  - Toujours privilégier la lecture via `project_map.json` pour obtenir les chemins officiels.

- Ne jamais supposer que :
  - L'outil peut "deviner" le contenu d'un fichier sans le lire explicitement.
