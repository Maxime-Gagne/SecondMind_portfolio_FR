# ProcesseurBrutePersistante

Type : Pipeline
Rôle principal : Consolider la mémoire épisodique brute en résumés granulaires et structurés pour alimenter la mémoire persistante à long terme.
Portée : Globale
Statut : Stable

---

## Description fonctionnelle

Le ProcesseurBrutePersistante agit comme un mécanisme de consolidation différée ("sommeil" du système). Il scanne les interactions brutes stockées dans l'historique, les groupe par session, et utilise un moteur LLM pour transformer des transcripts volumineux en fiches de résumés cohérentes. Ces micro-résumés sont ensuite classifiés, indexés et vectorisés individuellement pour une récupération sémantique précise.

---

## Objectifs

- Réduire la charge cognitive du système en remplaçant les dialogues bruts par des synthèses structurées.
- Garantir le maintien de l'intention globale à travers une session (re-classification contextuelle).
- Automatiser l'enrichissement du dataset d'entraînement pour le classifieur d'intentions.
- Assurer la persistance à long terme des connaissances acquises durant les échanges.

---

## Non-objectifs

Ce composant :
- N’a pas pour but de :
  - Traiter les messages en temps réel (fonctionne par batch après un timeout).
  - Modifier les fichiers d'historique originaux (il les marque comme traités).
  - Interagir directement avec l'utilisateur.

---

## Responsabilités

Ce composant est responsable de :
- Le regroupement chronologique des fichiers JSON par `session_id`.
- La gestion du cycle de vie des sessions (détection du timeout de 4h).
- L'orchestration du streaming LLM pour l'analyse globale des transcripts.
- La génération de fichiers JSON individuels par interaction dans le dossier `persistante`.
- La synchronisation des index vectoriels (FAISS) et textuels (Whoosh) pour chaque nouveau résumé.
- L'injection des paires (prompt réel / intention consolidée) dans l'AutoDatasetBuilder.

Ce composant n’est jamais responsable de :
- La suppression physique des logs bruts.

---

## Interfaces logiques

Expose :
- `traiter_batch_differe()` : Point d'entrée pour lancer le cycle de consolidation sur tous les fichiers en attente.

Consomme :
- `Interaction` (Dataclass) : Modèle pour la reconstruction des échanges résumés.
- `MoteurLLM` : Pour la capacité de synthèse et de classification sémantique.
- `AutoDatasetBuilder` : Pour la transmission des données de fine-tuning.

---

## Invariants

- Cohérence de l'Intention : Le sujet réel d'une session (ex: Script) prime sur la classification isolée d'un message (ex: Salutation).
- Atomicité : Un fichier historique n'est marqué comme "traité" qu'après la réussite confirmée de sa vectorisation et de son archivage persistant.
- Format : Chaque sortie doit être validée par `auditor.valider_format_sortie`.

---

## Dépendances conceptuelles

Dépend de :
- AgentRecherche / MoteurVectoriel : Pour la mise à jour des index après consolidation.
- AgentAuditor : Pour la localisation des dossiers historiques et persistants.

N’est jamais dépendant de :
- AgentParole : La construction des prompts de synthèse est interne au processeur.

---

## Contraintes connues

- Latence : Le traitement global peut être long selon le nombre de messages dans la session.
- Dépendance LLM : La qualité des résumés dépend strictement de la fenêtre de contexte du moteur de synthèse.

---

## Signaux d’interprétation pour l’IA

- Ce composant ne doit jamais être interprété comme :
  - Un agent de conversation ou un moteur de recherche.

- Si une ambiguïté apparaît :
  - Toujours privilégier la précision du résumé sur la rapidité de traitement.

- Ne jamais supposer que :
  - Une session en cours sera consolidée avant d'avoir atteint le délai de timeout défini.
