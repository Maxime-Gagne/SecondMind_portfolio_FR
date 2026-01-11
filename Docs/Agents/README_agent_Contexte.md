# AgentContexte

Type : Cognitif
Responsabilité primaire : Orchestrer la récupération, le filtrage et le formatage intelligent du contexte (mémoire, règles et historique) pour chaque requête utilisateur.
Statut : Stable

---

## Rôle fonctionnel

- Fonction principale : Gère le pipeline de tri sémantique pour fournir à l'agent de génération un contexte complet et pertinent (historique, règles actives, documentation et souvenirs).
- Problème résolu : Prévient l'amnésie conversationnelle et évite la surcharge d'informations inutiles en sélectionnant uniquement les éléments de mémoire les plus pertinents.
- Résultat produit : Un objet `ResultatContexte` validé contenant la "vérité" contextuelle du moment.

---

## Périmètre

L’agent :
- Fait :
  - Maintient et tronque l'historique de la conversation en cours (RAM).
  - Assure la continuité entre les sessions en rechargeant les derniers échanges depuis le disque.
  - Associe dynamiquement des règles spécifiques (IDs) ou des catégories (Tags) en fonction du contenu de la requête.
  - Filtre et classe les souvenirs (RAG) par score de pertinence via l'AgentJuge.
  - Récupère les protocoles d'alerte critiques en cas de besoin de gouvernance.

- Ne fait jamais :
  - N'effectue de recherche vectorielle brute lui-même (délègue à AgentRecherche).
  - Ne prend de décision finale sur la réponse à fournir à l'utilisateur.

---

## Contrat logique

### Entrées attendues
- ResultatIntention : Analyse de la requête (sujet, intention).
- ResultatRecherche : Liste brute des souvenirs et règles trouvés par le moteur de recherche.

### Sorties garanties
- ResultatContexte : Structure unifiée incluant l'historique, les règles actives, la documentation (READMEs) et les souvenirs filtrés.

---

## Invariants

- Garantie de non-vacuité : Si aucun souvenir, règle ou README n'est trouvé, l'agent injecte systématiquement un contenu par défaut (fallback).
- Validation de sortie : Le résultat final doit impérativement passer par `auditor.valider_format_sortie`.
- Continuité : L'historique chargé au démarrage doit respecter la limite stricte définie par la configuration (max_echanges).

---

## Dépendances conceptuelles

Dépend de :
- AgentRecherche : Pour la récupération physique des données sur le disque.
- AgentJuge : Pour l'évaluation de la pertinence sémantique (scoring).
- AgentMemoire (via Auditor) : Pour localiser les chemins de stockage de l'historique.

N’est jamais dépendant de :
- AgentParole : Il ne communique pas directement avec l'utilisateur.

---

## Modes d’échec connus

- Si le répertoire historique est introuvable → alors l'agent logue un avertissement et démarre avec un historique vide.
- Limite connue : La détection de règles repose sur des expressions régulières (Regex), ce qui nécessite une configuration YAML précise.

---

## Signaux d’interprétation pour l’IA

- Cet agent ne doit jamais être utilisé pour :
  - Inventer des règles qui ne figurent pas dans le système.

- Si une action semble ambiguë :
  - Prioriser systématiquement le chargement des règles de type "truth" (Vérité Suprême).

- Ne jamais supposer que :
  - Le contexte mémoire est suffisant sans inclure l'historique conversationnel récent.
