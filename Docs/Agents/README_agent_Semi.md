# AgentSemi (Orchestrateur Central)

**Type** : Cognitif (Chef d'Orchestre)
**Responsabilité primaire** : Coordonner le flux de pensée "Hub & Spoke", maintenir l'état de la session et synchroniser tous les sous-agents.
**Statut** : Stable (Production Grade)

---

## Rôle fonctionnel

- **Fonction principale** : Agit comme le "Runtime" du système. Il reçoit l'entrée utilisateur, orchestre la détection d'intention, le RAG, l'inférence LLM et l'exécution des outils.
- **Problème résolu** : Évite le couplage direct entre les composants (Memoire, Parole, Recherche) en centralisant la logique de flux.
- **Résultat produit** : Une réponse utilisateur streamée (token par token) enrichie d'effets de bord (sauvegarde mémoire, feedback, logs).

---

## Périmètre

L’agent :
- **Fait** :
  - Initialise et injecte les dépendances de tous les autres agents (Recherche, Memoire, Juge, etc.).
  - Gère la "Boucle de Pensée" : Intention -> Contexte -> Prompt -> LLM -> Outil -> Réponse.
  - Maintient l'état de la session (ID session, historique immédiat, fichiers actifs).
  - Exécute les commandes système prioritaires (`+1`, `!!!`, `NOUVEAU_CHAT`).

- **Ne fait jamais** :
  - Ne génère pas le prompt final lui-même (délégué à `AgentParole`).
  - Ne stocke pas les vecteurs lui-même (délégué à `AgentMemoire`).
  - Ne juge pas la pertinence sémantique (délégué à `AgentJuge`).

---

## Contrat logique

### Entrées attendues
- **Prompt Utilisateur (str)** : La requête brute (ex: "Analyse ce fichier").
- **ID Session (str)** : L'identifiant unique pour la continuité conversationnelle.
- **Modificateurs (Optional)** : Flags pour forcer le mode `web`, `debug` ou `manual_context`.

### Sorties garanties
- **Stream de Tokens (Generator)** : La réponse textuelle en temps réel pour l'interface.
- **Side Effects (Async)** : Sauvegarde de l'interaction, mise à jour des stats et extraction de code en arrière-plan.

---

## Invariants

- **Invariant de Continuité** : Une session doit toujours avoir un historique chargé (soit vide, soit restauré) avant la première inférence.
- **Invariant de Gouvernance** : Tout prompt contenant `!!!` doit déclencher le protocole ALERTE et contourner le flux standard.
- **Invariant de Non-Blocage** : Les tâches lourdes (sauvegarde vectorielle, indexation code) doivent toujours être exécutées dans des threads démons (`post_traitement_async`).

---

## Dépendances conceptuelles

Dépend de :
- **Tous les Agents** : En tant que Hub, il a besoin de `AgentRecherche`, `AgentMemoire`, `AgentParole`, `AgentJuge` pour fonctionner.
- **MoteurLLM** : Pour l'inférence brute.

N’est jamais dépendant de :
- **Interface Utilisateur** : Il est agnostique du frontend (Flask, Console, Discord) car il communique via des générateurs standards.

---

## Modes d’échec connus

- **Si le LLM ne répond pas (Timeout)** → Le stream s'arrête proprement et une erreur est loguée, mais le système ne crash pas (Try/Catch global).
- **Si une boucle d'outils infinie est détectée** → Un compteur `step_count` force l'arrêt après 10 itérations pour rendre la main à l'utilisateur.
- **Limite connue** : Le basculement en mode "JSON Caché" pour l'appel d'outil peut parfois laisser fuiter quelques tokens avant d'être intercepté si le LLM est très rapide.

---

## Signaux d’interprétation pour l’IA

- **Ne jamais supposer que** : L'AgentSemi a une "mémoire" propre. Il doit toujours interroger `AgentContexte` pour savoir ce qui s'est dit avant.
- **Si une action semble ambiguë** : L'AgentSemi privilégiera toujours le flux standard (RAG) plutôt que l'exécution d'outil autonome, sauf si le modèle produit un JSON explicite.
