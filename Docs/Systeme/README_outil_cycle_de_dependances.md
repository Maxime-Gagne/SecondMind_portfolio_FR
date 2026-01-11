# CycleDependancesTool

Type : Infrastructure / Pipeline
Rôle principal : Détecter et isoler les dépendances circulaires entre les modules pour garantir une architecture acyclique et stable.
Portée : Globale
Statut : Stable

---

## Description fonctionnelle

Ce composant est un analyseur de topologie logicielle qui transforme la cartographie du système en un graphe dirigé de dépendances. Il utilise un algorithme de recherche en profondeur (DFS) pour identifier mathématiquement les cycles entre les modules. Cela permet de valider que les agents ne sont pas enfermés dans des boucles d'importation ou de couplage trop fortes.


---

## Objectifs

- Extraire les relations de dépendances à partir du fichier `code_architecture.json`.
- Identifier et lister chaque cycle de dépendance de manière exhaustive.
- Fournir une vue canonique (dédoublonnée) des cycles pour faciliter le diagnostic.

---

## Non-objectifs

Ce composant :
- N’a pas pour but de :
  - Modifier le code source pour rompre les cycles automatiquement.
  - Analyser les dépendances au niveau granulaire des fonctions (limité au niveau des modules).
  - Générer lui-même les métadonnées d'architecture.

---

## Responsabilités

Ce composant est responsable de :
- La construction du graphe dirigé à partir des racines d'importation (`outgoing_edges`).
- La détection algorithmique des cycles par DFS avec gestion d'une pile de récursion.
- La normalisation des cycles (rotation) pour éviter les signalements redondants.
- L'affichage des alertes et des conseils de refactorisation en cas de violation.

Ce composant n’est jamais responsable de :
- La validation de la logique interne ou du comportement des agents.

---

## Interfaces logiques

Expose :
- `valider_dependances()` : Déclenche le cycle complet (Chargement -> Graphe -> Détection -> Affichage).
- `trouver_cycles()` : Retourne la liste des cycles détectés sous forme de listes de modules.

Consomme :
- `code_architecture.json` : Source de données structurelles générée par le moteur vectoriel.

---

## Invariants

- Unicité du signalement : Un cycle détecté est représenté sous une forme canonique unique.
- Indépendance du chemin : Le calcul reste exact indépendamment de la localisation racine du projet.

---

## Dépendances conceptuelles

Dépend de :
- `MoteurVecteurCode` : Fournisseur de l'architecture JSON nécessaire au graphe.
- `MEMOIRE_DIR` : Emplacement physique des données d'architecture.

N’est jamais dépendant de :
- Aucun agent cognitif ou moteur LLM (analyse 100% déterministe).

---

## Contraintes connues

- Dépendance aux données : Si le moteur vectoriel n'a pas été lancé, l'outil ne peut pas fonctionner.
- Portée : Ne détecte pas les cycles "cachés" par des imports dynamiques à l'intérieur des méthodes.

---

## Signaux d’interprétation pour l’IA

- Ce composant ne doit jamais être interprété comme :
  - Un agent capable de refactoriser le système de manière autonome.
- Si une ambiguïté apparaît :
  - Considérer que tout cycle détecté est une anomalie prioritaire bloquant la stabilité architecturale.
- Ne jamais supposer que :
  - Le système est sain si le fichier `code_architecture.json` est manquant ou obsolète.
