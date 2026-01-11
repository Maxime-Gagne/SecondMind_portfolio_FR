# Contrats d'interface

Type : Infrastructure
Rôle principal : Agir comme la source de vérité absolue pour le vocabulaire, les énumérations et les structures de données (Dataclasses) échangées entre les agents.
Portée : Globale
Statut : Stable

---

## Description fonctionnelle

Ce composant centralise les définitions techniques de tous les objets de transit du système. Il définit le langage commun (Enums) et les contraintes de formatage (Dataclasses) nécessaires pour assurer une communication inter-agents fluide et sans erreurs de type. Il inclut également des utilitaires de sérialisation JSON personnalisés pour gérer les types complexes comme les Enums, les Chemins (Path) et les Dates.

---

## Objectifs

- Standardiser les échanges de données pour éviter les désynchronisations entre agents.
- Fournir un vocabulaire strict (Sujet, Action, Catégorie) pour la classification des intentions.
- Garantir la validation des données dès leur instanciation via des méthodes `__post_init__`.

---

## Non-objectifs

Ce composant :
- N’a pas pour but de :
  - Exécuter de la logique métier ou des traitements de données.
  - Stocker physiquement des données (il ne définit que les modèles).

---

## Responsabilités

Ce composant est responsable de :
- Définir les Enums flexibles (supportant la normalisation de texte et d'accents).
- Maintenir les structures des métadonnées (MetadataFichier, MetadataPipeline) pour la traçabilité.
- Définir les formats de sortie de chaque agent (ResultatIntention, ResultatRecherche, ResultatContexte, etc.).
- Fournir les structures de "Prompts Standardisés" pour l'agent Parole.

Ce composant n’est jamais responsable de :
- L'instanciation des agents ou de la gestion des dépendances.

---

## Interfaces logiques

Expose :
- `Sujet`, `Action`, `Categorie` : Vocabulaire pour l'analyse d'intention.
- `Interaction` : Objet final consolidé pour la sauvegarde sur disque.
- `StandardPrompt` : Structure complète pour la génération de réponses.

Consomme :
- `EnumFlexible` : Pour la robustesse des énumérations.
- `Pydantic` & `Dataclasses` : Pour la validation et la structure.

---

## Invariants

- Toute communication inter-agents DOIT utiliser ces contrats.
- Ce fichier est la référence unique ; aucune Dataclass d'échange ne doit être définie localement dans un agent.

---

## Dépendances conceptuelles

Dépend de :
- `agentique.base.utils_text` : Pour les utilitaires de texte et Enums.

N’est jamais dépendant de :
- Aucun agent spécifique (Semi, Memoire, etc.) : il doit rester à la base de la pyramide des imports.

---

## Contraintes connues

- Toute modification d'un contrat ici nécessite souvent une mise à jour de la logique de validation dans l'Auditor.
- L'utilisation de Pydantic et Dataclasses impose une rigueur stricte sur les types optionnels.

---

## Signaux d’interprétation pour l’IA

- Ce composant ne doit jamais être interprété comme :
  - Un simple fichier de configuration ; c'est le "code génétique" des données du système.

- Si une ambiguïté apparaît :
  - La définition présente dans ce fichier prévaut sur toute autre documentation.

- Ne jamais supposer que :
  - Un agent peut envoyer un dictionnaire brut si une Dataclass correspondante existe ici.
