# SemiCode IDE

Type : Interface
Rôle principal : Fournir un environnement de développement intégré (IDE) permettant d'éditer, d'exécuter et de déboguer du code en collaboration directe avec l'assistant Semi.
Portée : Globale
Statut : Stable

---

## Description fonctionnelle

SemiCode IDE est une interface de développement web complète qui intègre l'éditeur de code industriel Monaco (le cœur de VS Code). Elle permet de naviguer dans l'arborescence du projet, d'éditer des fichiers (Python, HTML, JS), et d'exécuter des scripts localement avec un retour terminal. L'assistant Semi y est intégré de manière contextuelle : il peut analyser le code ouvert ou sélectionné pour proposer des corrections ou des optimisations directement applicables dans l'éditeur.

---

## Objectifs

- Offrir une interface de programmation robuste et fluide au sein de l'écosystème SecondMind.
- Faciliter la collaboration Homme-Machine pour la génération et le refactoring de code.
- Permettre l'exécution rapide et le test de scripts atomiques avec visualisation immédiate de l'output.

---

## Non-objectifs

Ce composant :
- N’a pas pour but de :
  - Remplacer un IDE professionnel complet pour des projets d'envergure multi-utilisateurs.
  - Gérer l'administration système du serveur hôte (limité au périmètre du projet).

---

## Responsabilités

Ce composant est responsable de :
- L'instanciation et la configuration de l'éditeur Monaco (thème, coloration syntaxique, raccourcis).
- La synchronisation bidirectionnelle des fichiers avec le système de fichiers via l'API.
- L'envoi de requêtes d'exécution de code et l'affichage des flux stdout/stderr dans le terminal intégré.
- L'enrichissement automatique des prompts envoyés à Semi avec le contexte du code actif ou sélectionné.
- L'application sécurisée (décodage Base64) des snippets de code suggérés par l'assistant dans l'éditeur.

Ce composant n’est jamais responsable de :
- La sécurité réseau du serveur d'exécution (délégué au backend).

---

## Interfaces logiques

Expose :
- `openFileFromTree(path)` : Charge un fichier du disque vers l'éditeur.
- `applyCode(encodedCode)` : Injecte du code généré par l'IA dans le document actif.
- `runCode()` : Déclenche l'exécution du script sur le serveur.

Consomme :
- `Monaco Editor API` : Pour toutes les fonctionnalités d'édition avancées.
- `HTTP API (/api/save_file, /api/execute_code, etc.)` : Pour les opérations disque et système.
- `AgentSemi (via /command)` : Pour l'assistance à la programmation.

---

## Invariants

- Le contenu de l'éditeur doit être synchronisé avec le backend lors de la sauvegarde ou de l'exécution.
- Toute injection de code par l'assistant doit supporter le mécanisme d'annulation (Undo) de l'éditeur.

---

## Dépendances conceptuelles

Dépend de :
- `Monaco Editor Library` : Indispensable pour l'interface de saisie.
- `Marked.js` : Pour le rendu des explications et blocs de code dans le volet assistant.

N’est jamais dépendant de :
- Un système de compilation lourd (utilise l'interpréteur Python déjà présent sur le système).

---

## Contraintes connues

- Limité aux langages supportés par l'installation Monaco (principalement Python, Web, JSON).
- L'auto-sauvegarde s'effectue toutes les 30 secondes pour éviter les pertes de données.
- Nécessite un accès aux APIs de fichiers du backend pour fonctionner.

---

## Signaux d’interprétation pour l’IA

- Ce composant ne doit jamais être interprété comme :
  - Un simple éditeur de texte (c'est un environnement d'exécution lié à l'assistant).

- Si une ambiguïté apparaît :
  - Prioriser systématiquement le texte sélectionné par l'utilisateur comme contexte immédiat.

- Ne jamais supposer que :
  - Le code affiché est exempt d'erreurs (le terminal et l'onglet "Problèmes" sont là pour la validation).
