# CodeExtractorManager

Type : Pipeline
Rôle principal : Détecter, extraire et analyser structurellement les fragments de code présents dans les flux textuels ou les fichiers.
Portée : Transversale
Statut : Stable

---

## Description fonctionnelle

Le CodeExtractorManager agit comme un processeur de flux spécialisé. Il scanne les réponses générées par les LLM pour isoler les blocs de code (Markdown), leur attribuer une identité unique (Hash) et effectuer une analyse statique (AST pour Python, Regex pour les autres langages) afin d'en extraire la substantifique moelle technique avant leur archivage.

---

## Objectifs

- Isoler proprement le code du texte explicatif dans les réponses du système.
- Fournir une carte d'identité technique (métadonnées) pour chaque fragment de code extrait.
- Garantir la traçabilité des extraits via un hachage MD5.

---

## Non-objectifs

Ce composant :
- N’a pas pour but de :
  - Exécuter le code extrait (ce n'est pas un interpréteur).
  - Corriger les erreurs de syntaxe (il se contente de les rapporter).
  - Gérer le stockage physique final (il délègue à l'AgentMemoire).

---

## Responsabilités

Ce composant est responsable de :
- La détection des blocs de code via des expressions régulières robustes.
- L'analyse syntaxique (AST) des fichiers Python pour identifier les classes, fonctions et imports.
- La génération de placeholders `<ARTIFACT_CODE...>` pour nettoyer les réponses textuelles.
- La production d'objets `AnalyseContenu` conformes aux contrats d'interface.

Ce composant n’est jamais responsable de :
- La prise de décision sur l'intégration du code dans le projet global.

---

## Interfaces logiques

Expose :
- `traiter_reponse_llm` : Transforme un texte brut en texte nettoyé + liste d'artefacts.
- `_analyser_contenu_code` : Moteur d'analyse multi-langages (Py, JS, HTML, CSS, JSON).

Consomme :
- `AnalyseContenu` / `ArtefactCode` : Modèles de données pour la structuration des sorties.

---

## Invariants

- Tout bloc de code extrait doit posséder un ID unique basé sur son contenu (déterminisme du hash).
- En cas d'échec de l'analyse AST (Python), le composant doit obligatoirement basculer sur un mode "Regex Fallback" pour ne pas perdre l'information.

---

## Dépendances conceptuelles

Dépend de :
- `agentique.base.contrats_interface` : Pour le respect des structures `ArtefactCode` et `AnalyseContenu`.
- Bibliothèque `ast` (Python) : Pour l'analyse structurelle profonde du code Python.

N’est jamais dépendant de :
- `AgentRecherche` ou `AgentCode` : Il traite la donnée brute sans se soucier de sa provenance ou de sa destination finale.

---

## Contraintes connues

- L'analyse des langages non-Python est limitée à une détection par Regex (moins précise qu'un véritable parser).
- La détection dépend de la présence correcte des balises Markdown (```) dans le texte source.

---

## Signaux d’interprétation pour l’IA

- Ce composant ne doit jamais être interprété comme :
  - Un compilateur ou un vérificateur de logique métier.

- Si une ambiguïté apparaît :
  - Prioriser l'extraction brute du contenu sur la finesse de l'analyse structurelle.

- Ne jamais supposer que :
  - Un snippet de code incomplet sera analysé avec succès par le moteur AST (prévoir le fallback systématique).
