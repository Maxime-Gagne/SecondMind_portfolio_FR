# AgentParole

Type : Cognitif
Responsabilité primaire : Construire le prompt ChatML final en assemblant dynamiquement les variables système, le profil utilisateur et le contexte métier pour guider le LLM.
Statut : Stable

---

## Rôle fonctionnel

- Fonction principale : Compile les données structurées (Interaction, Souvenirs, Code) en instructions textuelles ChatML exploitables par le moteur LLM.
- Problème résolu : Centralise la logique de mise en forme des prompts pour garantir une structure cohérente, JSON-safe et respectueuse des limites de contexte.
- Résultat produit : Une chaîne de caractères formatée (Prompt) prête pour l'inférence LLM.

---

## Périmètre

L’agent :
- Fait :
  - Aiguille les requêtes vers des constructeurs de prompts spécifiques (Standard, Code, Inspection, Web, Protocole).
  - Injecte dynamiquement le Profil Utilisateur (Maxime) et le Résumé Système (Amnésie/Staging) dans les templates.
  - Formate les sections de support : Documentation technique, Règles de gouvernance, Contexte mémoire et Historique de conversation.
  - Trace l'utilisation des champs via `TrackedDataclass` pour assurer qu'aucune donnée de contexte n'est ignorée.
  - Met à jour le cache du "Prompt Viewer" pour la supervision en temps réel.

- Ne fait jamais :
  - N'invente pas de contenu : il est un pur constructeur de structure ("Prompt Builder").
  - Ne communique jamais directement avec le moteur LLM (rôle de l'AgentSemi ou du MoteurLLM).

---

## Contrat logique

### Entrées attendues
- Dataclasses de Prompt (StandardPrompt, StandardPromptCode, etc.) : Objets contenant les briques de données à assembler.
- Configuration YAML : Sources de vérité pour les templates d'instructions système.

### Sorties garanties
- Prompt ChatML (str) : La séquence textuelle finale incluant les balises de rôles (<|im_start|>system/user/assistant).

---

## Invariants

- Validation Auditor : Chaque objet d'entrée est wrappé dans une `TrackedDataclass` pour valider que tous les champs critiques sont utilisés dans le prompt final.
- Robustesse Template : Les variables globales ({profil_utilisateur}, {contenu_actuel_resume}) sont injectées via un mécanisme de remplacement sécurisé pour éviter les crashs sur les accolades JSON.
- Non-vacuité Mémoire : Si une liste de souvenirs est vide alors que le type de prompt l'exige, l'agent lève une erreur explicite.

---

## Dépendances conceptuelles

Dépend de :
- Auditor : Pour la validation de l'utilisation des champs et la résolution des chemins de configuration.
- AgentContexte : Pour la récupération de l'historique de continuité lors d'un nouveau chat.

N’est jamais dépendant de :
- Moteurs d'inférence : Il s'arrête à la génération de la chaîne de caractères, sans se soucier de l'exécution.

---

## Modes d’échec connus

- Si un template contient des clés de formatage inconnues -> alors l'agent bascule sur une concaténation brute pour éviter l'échec total.
- Limite connue : La validation d'utilisation complète par l'Auditor peut signaler des faux-positifs sur des champs optionnels non prévus dans certains constructeurs.

---

## Signaux d’interprétation pour l’IA

- Cet agent ne doit jamais être utilisé pour :
  - Modifier le ton ou l'identité de Semi (ces règles sont fixées dans `config_parole.yaml`).

- Si une action semble ambiguë :
  - Toujours inclure les balises de fin de rôle (<|im_end|>) pour éviter les fuites de contexte au LLM.

- Ne jamais supposer que :
  - Le LLM connaît le profil de Maxime si la variable `{profil_utilisateur}` n'a pas été explicitement injectée par l'agent.
