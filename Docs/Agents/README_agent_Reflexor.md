# AgentReflexor

Type : Gouvernance / Cognitif
Responsabilité primaire : Analyser les incidents et les feedbacks utilisateur pour assurer l'auto-correction comportementale et l'amélioration continue du système.
Statut : Stable

---

## Rôle fonctionnel

- Fonction principale : Pilote la boucle d'introspection du système en analysant les échecs et en consignant des traces réflexives structurées dans le journal de bord.
- Problème résolu : Permet au système de comprendre pourquoi il a échoué (hallucination, biais, erreur logique) et d'apprendre de ses erreurs pour éviter leur répétition.
- Résultat produit : Fiches d'incidents standardisées (Markdown) et règles de correction comportementale injectées en mémoire.

---

## Périmètre

L’agent :
- Fait :
  - Déclenche la boucle réflexive sur signalement utilisateur explicite ("!!!").
  - Analyse l'incident via le LLM pour identifier l'erreur commise, le type d'écart et l'hypothèse causale.
  - Recherche des précédents similaires dans la mémoire vectorielle pour contextualiser l'anomalie.
  - Génère des actions correctives concrètes (Staging) sous forme de règles de comportement.
  - Enregistre et catégorise le feedback utilisateur (Score, Tags, Mémoire).

- Ne fait jamais :
  - Ne tente de justifier une erreur auprès de l'utilisateur (il reste clinique et factuel).
  - Ne modifie directement les agents exécutifs sans passer par la journalisation réflexive.

---

## Contrat logique

### Entrées attendues
- Prompt d'erreur (str) : La requête ou le signalement de l'anomalie.
- Historique (List[str]) : Les derniers échanges ayant mené à l'incident.
- Feedback (Dict) : Score de satisfaction et métadonnées associées.

### Sorties garanties
- EntreeJournalReflexif : Dataclass validée contenant l'analyse complète de l'incident.
- Trace Markdown : Version textuelle structurée de l'entrée réflexive pour le journal.

---

## Invariants

- Classification stricte : Tout écart doit être classé selon l'Enum `TypeEcart` (Hallucination, Logique, Gouvernance, etc.).
- Validation de sortie : Toute entrée réflexive générée doit passer par `auditor.valider_format_sortie`.
- Persistance : Les traces réflexives sont systématiquement vectorisées et indexées dans Whoosh pour être réutilisables.

---

## Dépendances conceptuelles

Dépend de :
- AgentMemoire : Pour l'écriture physique des traces et l'accès à la mémoire vectorielle.
- MoteurLLM : Pour l'analyse métacognitive et la génération des hypothèses causales.
- Auditor : Pour la validation des contrats de sortie.

N’est jamais dépendant de :
- AgentParole : Il n'influence pas la forme de la réponse, seulement le fond via les règles de correction.

---

## Modes d’échec connus

- Si le parsing JSON de l'analyse LLM échoue → alors l'agent bascule sur un mode "Fallback Technique" pour ne pas perdre la trace de l'incident.
- Limite connue : L'analyse causale dépend de la qualité du moteur LLM injecté (MiniLLM vs LargeLLM).

---

## Signaux d’interprétation pour l’IA

- Cet agent ne doit jamais être utilisé pour :
  - Effacer ou masquer des erreurs commises par le système.

- Si une action semble ambiguë :
  - Toujours privilégier la classification "Gouvernance" en cas de doute sur la nature de l'erreur.

- Ne jamais supposer que :
  - Une correction est appliquée tant qu'elle n'a pas été journalisée et indexée par l'AgentMemoire.
