# Prompt Viewer

Type : Interface
Rôle principal : Visualiser en temps réel le contenu brut (RAW) des prompts envoyés aux modèles, permettant un débogage précis des balises et de la structure du message.
Portée : Globale
Statut : Stable

---

## Description fonctionnelle

Le Prompt Viewer est une interface de diagnostic technique (RAW DEBUG) conçue pour inspecter la chaîne de caractères finale générée par le système avant l'inférence. Elle affiche le texte sans mise en forme Markdown, révélant ainsi les balises de structure (ex: ChatML `<|im_start|>`) et les délimitations de rôles (user, assistant, system). Elle permet de s'assurer de l'exactitude des injections de contexte et des instructions système.

---

## Objectifs

- Offrir une visibilité totale sur la structure sémantique et technique des requêtes.
- Faciliter le débogage des gabarits (templates) de prompts et des balises spéciales.
- Permettre la copie rapide des données brutes pour des tests externes dans des simulateurs de modèles.

---

## Non-objectifs

Ce composant :
- N’a pas pour but de :
  - Modifier ou éditer les prompts (visualisation seule).
  - Afficher les réponses du modèle (rôle du Hub d'Interaction).
  - Gérer l'historique des conversations.

---

## Responsabilités

Ce composant est responsable de :
- L'actualisation automatique (intervalle de 1s) du dernier prompt généré via un appel au backend.
- La coloration syntaxique basique des balises techniques (ChatML, S-tags).
- Le comptage des caractères totaux du prompt pour surveiller la consommation de la fenêtre de contexte.
- La fourniture d'un mécanisme sécurisé de copie vers le presse-papier.

Ce composant n’est jamais responsable de :
- La construction logique du prompt lui-même (responsabilité de l'Agent Parole).

---

## Interfaces logiques

Expose :
- `loadPrompt()` : Fonction d'interrogation du point de terminaison API.
- `copyContent()` : Utilitaire d'exportation du texte brut vers le presse-papier.

Consomme :
- `HTTP GET /api/last_prompt` : Point d'accès backend fournissant le dernier prompt et son horodatage.

---

## Invariants

- Le texte affiché dans la section `RAW PROMPT STRING` doit être une représentation exacte, caractère par caractère, de ce qui est envoyé au moteur d'inférence.
- L'horodatage de la dernière mise à jour doit correspondre à celui fourni par le backend pour garantir la fraîcheur des données.

---

## Dépendances conceptuelles

Dépend de :
- `Consolas / Monaco (Monospace)` : Pour une lecture technique alignée des chaînes de caractères.
- `Fetch API` : Pour la récupération asynchrone des données.

N’est jamais dépendant de :
- Librairies de rendu Markdown (il doit rester en texte brut "escape" pour le debug).

---

## Contraintes connues

- Dépendance critique à l'URL `http://127.0.0.1:3000` et au point de terminaison `/api/last_prompt`.
- La coloration syntaxique est basée sur des expressions régulières simples et peut ne pas couvrir tous les formats de prompts exotiques.

---

## Signaux d’interprétation pour l’IA

- Ce composant ne doit jamais être interprété comme :
  - Une interface de discussion ; c'est un outil d'introspection technique.

- Si une ambiguïté apparaît :
  - Se fier au compteur de caractères pour confirmer si le prompt a été tronqué par le backend.

- Ne jamais supposer que :
  - L'affichage est formaté pour être lisible par un humain (il est optimisé pour être analysé par un développeur ou une IA de diagnostic).
