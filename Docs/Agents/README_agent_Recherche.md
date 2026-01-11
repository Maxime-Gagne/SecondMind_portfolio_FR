# AgentRecherche

Type : Exécutif / Support
Responsabilité primaire : Localiser et extraire toute information pertinente (mémoire, code, web) avec une performance quasi-instantanée pour alimenter la réflexion du système.
Statut : Stable

---

## Rôle fonctionnel

- Fonction principale : Orchestre une suite d'outils de recherche hybrides (Vectoriel, Full-Text, OSINT) pour fournir des preuves factuelles et du contexte technique aux autres agents.
- Problème résolu : Élimine la latence d'accès aux données volumineuses et permet une exploration approfondie du Web ("Deep Research") sans intervention humaine.
- Résultat produit : Des objets `ResultatRecherche` contenant des `Souvenirs` (extraits de fichiers, snippets de code ou synthèses web) validés techniquement.
- AgentRecherche est le point d’unification de toutes les stratégies de retrieval.
---

## Périmètre

L’agent :
- Fait :
  - Recherche "Verbatim" : Retrouve des citations exactes dans l'historique via Whoosh et vérification disque.
  - Recherche "Projet" : Localise des fichiers sources (.py, .yaml) via Everything en respectant les filtres de sécurité.
  - Recherche "Web" : Exécute des boucles itératives (Planifier -> Chercher -> Scraper -> Évaluer) pour répondre à des objectifs complexes.
  - Gestion de la Continuité : Récupère les N derniers échanges chronologiques avec support de "Swap" (échange du brut contre un résumé consolidé).
  - Cartographie : Fournit une vision globale de l'arborescence du projet via le `project_map.json`.

- Ne fait jamais :
  - N'altère ni ne supprime les fichiers indexés.
  - Ne génère de contenu sans source (il est un agent de "Preuves").

---

## Contrat logique

### Entrées attendues
- ResultatIntention : Pour le boosting sémantique des résultats de recherche.
- Requête (str) : Termes de recherche, patterns de fichiers ou objectifs de recherche web.
- Type de recherche : Spécification du moteur à utiliser (code, verbatim, concept, web).

### Sorties garanties
- ResultatRecherche : Conteneur de souvenirs avec métadonnées de performance.
- Souvenir : Atome d'information incluant le contenu brut, le titre de la source et un score de pertinence.

---

## Invariants

- Fail-Fast : L'agent crash immédiatement à l'initialisation si l'exécutable `es.exe` (Everything) est introuvable.
- Intégrité des sorties : Toute donnée retournée est soumise à `auditor.valider_format_sortie`.
- Lecture Robuste : Utilisation forcée de l'encodage UTF-8 avec remplacement des caractères invalides pour garantir la lecture sans crash.

---

## Dépendances conceptuelles

Dépend de :
- AgentMemoire / Moteur Vectoriel : Pour la recherche sémantique par similarité (FAISS).
- Everything (es.exe) : Pour la localisation instantanée de fichiers sur Windows.
- Whoosh : Pour l'indexation plein texte et la recherche par classification (tags/sujets).
- DuckDuckGo / BeautifulSoup : Pour l'exploration et l'extraction de données web.

N’est jamais dépendant de :
- Interface Utilisateur : Ses résultats sont toujours consommés par un agent intermédiaire (ex: AgentContexte).

---

## Modes d’échec connus

- Si le serveur de documentation web ou DuckDuckGo est indisponible → alors l'agent bascule en mode dégradé (recherche interne uniquement).
- Limite connue : L'indexation Whoosh nécessite une maintenance (reconstruction) si de nombreux fichiers sont ajoutés manuellement hors pipeline.
- Si un fichier README est mal nommé (non-respect de `README_*.md`) → il est ignoré par le moteur de recherche de documentation.

---

## Signaux d’interprétation pour l’IA

- Cet agent ne doit jamais être utilisé pour :
  - Deviner le contenu d'un fichier sans le lire explicitement.

- Si une action semble ambiguë :
  - Toujours privilégier la recherche "Projet" si la requête mentionne une extension de fichier (.py, .yaml).

- Ne jamais supposer que :
  - Un résultat de recherche web est une vérité absolue sans vérifier le score de pertinence/suffisance interne.
