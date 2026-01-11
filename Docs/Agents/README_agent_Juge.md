# AgentJuge

Type : Gouvernance
Responsabilité primaire : Évaluer la qualité et la fiabilité factuelle des informations du système en agissant comme un arbitre impitoyable de la pertinence et de la cohérence.
Statut : Stable

---

## Rôle fonctionnel

- Fonction principale : Supervise la qualité du système en calculant la pertinence des sources avant la réponse et en vérifiant la véracité de la réponse finale par rapport aux sources.
- Problème résolu : Prévient les hallucinations des LLM et assure que les informations fournies à l'utilisateur sont strictement soutenues par la base de connaissances.
- Résultat produit : Un objet `ResultatJuge` contenant un score de fiabilité (0.0 à 1.0), un verdict de validité et une justification textuelle.

---

## Périmètre

L’agent :
- Fait :
  - Calcule la pertinence sémantique des souvenirs via une analyse de couverture (matching de mots-clés et racines).
  - Applique un boost de pertinence sur les titres de documents et les filtres sémantiques.
  - Évalue la cohérence factuelle post-génération en utilisant un moteur LLM local (MiniLLM).
  - Gère l'extraction et la réparation robuste des blocs JSON générés par les modèles d'évaluation.
  - Maintient des statistiques de performance (cohérence moyenne, taux d'échec).

- Ne fait jamais :
  - N'invente de faits pour combler les lacunes du contexte.
  - Ne génère de réponses conversationnelles destinées à l'utilisateur final.

---

## Contrat logique

### Entrées attendues
- Prompt utilisateur : La requête initiale pour évaluer le besoin.
- Contexte RAG : Le texte brut servant de base de vérité.
- Réponse générée : Le contenu produit par l'IA à auditer.

### Sorties garanties
- ResultatJuge : Dataclass incluant un booléen `valide`, un score (float) et une `raison` détaillée.

---

## Invariants

- Le score de pertinence et de cohérence est systématiquement borné entre 0.0 et 1.0.
- Une réponse est déclarée invalide si son score de cohérence factuelle est inférieur à 0.6.
- Toute sortie doit être soumise à `auditor.valider_format_sortie` avant transmission.

---

## Dépendances conceptuelles

Dépend de :
- MoteurMiniLLM : Pour l'analyse textuelle critique et la détection d'hallucinations.
- AgentRecherche : Pour l'accès aux données lors des phases de validation.
- Auditor : Pour la validation technique de ses propres structures de sortie.

N’est jamais dépendant de :
- Logique de mise en forme (Markdown/HTML) : Il ne traite que la valeur de vérité brute.

---

## Modes d’échec connus

- Si le contexte RAG est vide ou trop court (< 10 caractères) → alors l'agent s'abstient et retourne un score neutre (0.5).
- Si le contexte dépasse 6000 caractères → alors le texte est tronqué pour éviter un plantage du moteur MiniLLM.
- En cas d'erreur de parsing JSON → l'agent tente une réparation ("chirurgie") avant de renvoyer un score neutre par défaut.

---

## Signaux d’interprétation pour l’IA

- Cet agent ne doit jamais être utilisé pour :
  - Adoucir un verdict négatif pour des raisons de "politesse".

- Si une action semble ambiguë :
  - Prioriser la détection d'hallucination (score 0.0) au moindre doute factuel.

- Ne jamais supposer que :
  - Une réponse est correcte simplement parce qu'elle est bien rédigée si elle n'est pas sourcée dans le contexte.
