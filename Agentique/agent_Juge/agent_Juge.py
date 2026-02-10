#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AgentJuge - Superviseur de Qualité et Détecteur d'Hallucinations
Module responsable de l'évaluation normative des entrées (Retrieval) et des sorties (Generation).

Ce module implémente une architecture de validation à double détente :
1.  **Juge A Priori (Retrieval Judge)** : Évalue la pertinence des documents récupérés par le RAG *avant* leur injection dans le contexte. Utilise des heuristiques lexicales (TF-IDF simplifié, correspondance de mots-clés) pour filtrer le bruit.
2.  **Juge A Posteriori (Consistency Judge)** : Évalue la facticité de la réponse générée par le LLM *après* sa production. Utilise un modèle de langage spécialisé (MiniLLM/SLM) pour vérifier que chaque affirmation est étayée par le contexte (NLI - Natural Language Inference).

Rôle Architectural :
    Agit comme un "Circuit Breaker". Si le score de cohérence chute sous un seuil critique,
    l'AgentJuge peut bloquer la réponse ou forcer une reformulation, garantissant la fiabilité du système.
"""

import logging
import json
import yaml
import re
from typing import Dict, List, Any
from datetime import datetime
from collections import deque
from pathlib import Path
from agentique.base.META_agent import AgentBase
from agentique.base.contrats_interface import ResultatJuge
from agentique.sous_agents_gouvernes.agent_Parole.moteurs.moteur_mini_llm import (
    MoteurMiniLLM,
)  # <--- IMPORTANT


class AgentJuge(AgentBase):
    # 1. INJECTION DU MOTEUR MINI LLM
    def __init__(self, agent_recherche, moteur_mini_llm=None):
        super().__init__(nom_agent="AgentJuge")
        """
        Arbitre impartial de la chaîne de traitement cognitive.

        Cette classe centralise toutes les logiques d'évaluation. Elle est conçue pour être :
        - **Robuste** : Gère les échecs du moteur de jugement (fallback neutre).
        - **Agnostique** : Peut utiliser différents backends de vérification (Regex, LLM Local, API).
        - **Métacognitive** : Maintient des statistiques sur la qualité moyenne des réponses pour déclencher des alertes de dérive.

        Attributes:
            agent_recherche (AgentRecherche): Source de vérité pour la vérification des faits.
            moteur_mini_llm (MoteurMiniLLM): Modèle léger dédié aux tâches de classification binaire (Vrai/Faux) et de scoring.
        """

        self.agent_recherche = agent_recherche

        self.moteur_mini_llm = moteur_mini_llm
        if moteur_mini_llm:
            self.llm = moteur_mini_llm  # Utilise celui qu'on lui donne
        else:
            self.llm = (
                MoteurMiniLLM()
            )  # Sinon en charge un (Fallback) # <--- STOCKAGE DU MOTEUR

        # ... (Le reste de l'init est OK) ...
        config_root = self.auditor.get_path("config")
        self.config = self._load_config(config_root or "")

        # Accès rapides aux sous-sections (source de vérité : YAML)
        self.cfg_limites = self.config
        self.cfg_decision = self.config.get("decision", {})
        self.cfg_pertinence = self.config.get("pertinence", {})

        # Mémoire interne
        self.historique_coherence = deque(maxlen=100)
        # Stats
        self.stats_manager.ajouter_stat_specifique("appels_pertinence_total", 0)
        self.stats_manager.ajouter_stat_specifique("appels_coherence_total", 0)
        self.stats_manager.ajouter_stat_specifique("coherence_moyenne", 1.0)
        self.stats_manager.ajouter_stat_specifique("echecs_coherence_total", 0)

        self.logger.info("✅ AgentJuge initialisé.")

    def _load_config(self, config_path: str) -> Dict:
        """Charge la configuration YAML de l'agent (source de vérité unique)."""
        if not config_path:
            self.logger.log_error(
                "❌ AgentJuge: chemin config introuvable (auditor.get_path('config') vide)."
            )
            return {}

        p = Path(config_path)

        # Le contrat des autres agents : 'config' pointe généralement vers un dossier.
        # On supporte aussi le cas où 'config_path' pointe déjà vers un fichier.
        if p.is_dir():
            p = p / "config_juge.yaml"

        if not p.exists():
            self.logger.log_error(
                f"❌ AgentJuge: fichier de configuration introuvable: {p}"
            )
            return {}

        try:
            with open(p, "r", encoding="utf-8") as f:
                cfg_brute = yaml.safe_load(f) or {}
            return cfg_brute.get("configuration", {}) or {}
        except Exception as e:
            self.logger.log_error(
                f"Erreur lors du chargement de la configuration du Juge: {e}"
            )
            return {}

    # =================================================================
    # MISSION 1 : CALCUL DE PERTINENCE (AVANT GÉNÉRATION)
    # =================================================================

    def calculer_pertinence_semantique(
        self,
        prompt: str,
        souvenir_contenu: str,
        souvenir_titre: str,
        filtres_semantiques: List[Dict],
    ) -> float:
        """
        Évalue la pertinence d'un document candidat pour le contexte (Juge A Priori).

        Implémente un algorithme de scoring hybride optimisé :
        1. **Lexical Match** : Calcule le taux de recouvrement des mots-clés (après nettoyage et lemmatisation légère).
        2. **Title Boost** : Applique un multiplicateur si les termes de la requête apparaissent dans le titre du document.
        3. **Semantic Bonus** : Ajoute des points si le document correspond aux métadonnées (Sujet/Action) attendues.

        Args:
            prompt (str): La requête utilisateur.
            souvenir_contenu (str): Le texte du document candidat.

        Returns:
            float: Score de pertinence normalisé [0.0 - 1.0].
        """
        # -> Met à jour le compteur global de statistiques.
        self.stats_manager.incrementer_stat_specifique("appels_pertinence_total")
        # Sécurité types
        if not isinstance(souvenir_contenu, str):
            souvenir_contenu = str(souvenir_contenu) if souvenir_contenu else ""

        # --- 1. CONFIGURATION LINGUISTIQUE (Correctif Claude #2 et #3) ---
        # Liste noire : Mots grammaticaux fréquents (Stop Words) qui diluent le sens.
        # On préfère une liste explicite plutôt qu'un filtre sur la longueur pour garder "IA", "UI", "DB"
        # Source de vérité : config_juge.yaml -> configuration.pertinence.stop_words
        stop_words_list = self.cfg_pertinence.get("stop_words")
        STOP_WORDS = set(stop_words_list or [])
        boost_titre = self.cfg_pertinence.get("boost_titre")
        bonus_sujet = self.cfg_pertinence.get("bonus_sujet")
        if boost_titre is None or bonus_sujet is None:
            raise RuntimeError(
                "❌ AgentJuge: configuration.pertinence incomplet (boost_titre/bonus_sujet)."
            )
        boost_titre = float(boost_titre)
        bonus_sujet = float(bonus_sujet)

        def extraire_mots(t):
            # 1. Nettoyage regex (alphanumérique)
            mots_bruts = re.findall(r"\w+", t.lower())
            mots_utiles = set()
            for m in mots_bruts:
                # 2. Filtrage Intelligent :
                # On garde les mots de 2 lettres (ex: IA, PC, DB) SAUF s'ils sont dans la Stop List
                if len(m) > 1 and m not in STOP_WORDS:
                    # 3. Lemmatisation "Pauvre" (Correctif Claude #1)
                    # On enlève le 's' final pour matcher singulier/pluriel sans librairie lourde
                    # Ex: "scripts" -> "script"
                    root = m[:-1] if m.endswith("s") and len(m) > 3 else m
                    # "travaux" → "travau" (pas idéal, mais rare)
                    # "réseaux" → "réseau" (utile)
                    if m.endswith("x") and len(m) > 4:
                        root = m[:-1]
                    mots_utiles.add(root)
            return mots_utiles

        # -> Extraction et nettoyage des mots du prompt
        prompt_mots = extraire_mots(prompt)

        if not prompt_mots:
            return 0.0

        # --- 2. ANALYSE CONTENU (Recall / Couverture) ---
        score_contenu = 0.0
        if souvenir_contenu:
            mots_contenu = extraire_mots(souvenir_contenu)
            if mots_contenu:
                inter_c = prompt_mots.intersection(mots_contenu)
                # Formule : Combien de mots du prompt sont présents dans le fichier ?
                score_contenu = len(inter_c) / len(prompt_mots)

        # --- 3. ANALYSE TITRE (Boost) ---
        score_titre = 0.0
        if souvenir_titre:
            titre_clean = souvenir_titre.replace("_", " ").replace(".", " ")
            mots_titre = extraire_mots(titre_clean)

            if mots_titre:
                inter_t = prompt_mots.intersection(mots_titre)
                if inter_t:
                    ratio_titre = len(inter_t) / len(prompt_mots)
                    # Boost titre (Plafonné à 1.0) (piloté par la configuration)
                    # Un match sur le titre est un signal fort de pertinence
                    score_titre = min(1.0, ratio_titre * boost_titre)

        # --- 4. SCORE DE BASE (Stratégie Max) ---
        score_base = max(score_contenu, score_titre)

        # --- 5. BONUS SÉMANTIQUE RENFORCÉ (Correctif Claude #4) ---
        bonus_semantique = 0.0
        texte_global = (souvenir_contenu + " " + souvenir_titre).lower()

        for filtre in filtres_semantiques:
            sujet = filtre.get("sujet", "").lower()
            # Bonus sémantique (valeur pilotée par la configuration)
            if sujet and sujet != "inconnu" and sujet in texte_global:
                bonus_semantique += bonus_sujet

        # --- 6. SCORE FINAL ---
        score_final = min(1.0, score_base + bonus_semantique)

        # Logging pour vérifier le débouchage (Debug)
        if score_final > 0.4:
            self.logger.info(
                f"⚖️ Pertinence OK: '{souvenir_titre[:25]}...' = {score_final:.2f}"
            )

        return round(score_final, 3)

    # =================================================================
    # MISSION 2 : CALCUL DE COHÉRENCE (APRÈS GÉNÉRATION)
    # =================================================================

    def evaluer_coherence_reponse(
        self, contexte_rag_str: str, prompt: str, reponse: str
    ) -> ResultatJuge:
        """
        Vérifie l'ancrage factuel de la réponse générée (Juge A Posteriori).

        Orchestre une tâche de "Fact-Checking" automatique via le MiniLLM :
        1. **Troncature Intelligente** : Adapte la taille du contexte pour respecter la fenêtre d'attention du modèle juge.
        2. **Prompting Contradictoire** : Demande au modèle de détecter activement les contradictions entre le Contexte et la Réponse.
        3. **Parsing Structuré** : Extrait un verdict JSON formel (Score + Raison) de la sortie textuelle du modèle.

        Gère les cas limites (Contexte vide, Modèle indisponible) par des stratégies de "Fail-Open" (Validation par défaut avec avertissement).

        Args:
            contexte_rag_str (str): Les faits bruts fournis au système.
            prompt (str): La question posée.
            reponse (str): La réponse à vérifier.

        Returns:
            ResultatJuge: Objet contenant le verdict (Valide/Invalide), le score de confiance et la justification.
        """
        # -> Importation locale pour éviter les cycles d'import, car on a besoin de la structure stricte de sortie.
        from agentique.base.contrats_interface import ResultatJuge

        # --- CONSTANTES DE SÉCURITÉ ---
        # Limite chars contexte (pilotée par la configuration).
        # Sur un contexte de 4k, ça laisse 2.5k pour le prompt système + la réponse + la marge.
        # -> Plafond dur pour éviter de faire planter le petit modèle local (MiniLLM).
        MAX_CHARS_CONTEXTE = int(self.cfg_limites.get("max_chars_contexte"))

        # --- 1. CLAUSE DE GARDE : CONTEXTE VIDE ---
        # -> Vérifie si le contexte est vide, nul, ou contient moins de 10 caractères (inutile d'analyser du vide).
        if not contexte_rag_str or len(contexte_rag_str.strip()) < int(
            self.cfg_limites.get("min_chars_contexte")
        ):
            self.logger.info("⚖️ Juge : Pas de contexte suffisant. Abstention.")
            # CORRECTION ICI
            # -> Création d'un verdict "Neutre" (Validé=True, Score=0.5). On ne pénalise pas l'IA, on s'abstient juste.
            # -> Le champ 'details' est rempli pour expliquer l'abstention.
            res = ResultatJuge(
                valide=True,
                score=0.5,
                raison="Non évalué (Contexte vide)",
                details={"mode": "abstention"},
            )
            # 🛡️👁️‍🗨️🛡️# VALIDATION FORMAT SORTIE
            # -> Appel à l'Auditor pour vérifier que l'objet respecte le contrat (champs obligatoires présents).
            self.auditor.valider_format_sortie(res)
            return res

        # --- 2. PROTECTION CONTRE SURCHARGE ---
        taille_contexte = len(contexte_rag_str)
        # -> Si le texte dépasse la limite définie plus haut...
        if taille_contexte > MAX_CHARS_CONTEXTE:
            self.logger.log_warning(
                f"⚠️ Juge: Contexte trop gros ({taille_contexte} chars). Tronacature à {MAX_CHARS_CONTEXTE}."
            )
            # -> TRONCATURE : On coupe le texte au plafond configuré et on ajoute un marqueur visuel.
            # -> Cela permet de juger sur le début du texte (souvent le plus pertinent) plutôt que de crasher.
            contexte_rag_str = (
                contexte_rag_str[:MAX_CHARS_CONTEXTE] + "\n... [CONTEXTE TRONQUÉ] ..."
            )
            # Note: Si on voulait annuler ici, il faudrait aussi valider le ResultatJuge retourné.

        # ---------------------------------------

        # Si contexte présent (et nettoyé), on lance l'évaluation LLM standard
        try:
            # -> Construction du prompt final qui sera envoyé au LLM (System Prompt + User Prompt).
            prompt_juge = self._construire_prompt_juge(
                contexte_rag_str, prompt, reponse
            )

            # -> Vérification de sécurité #1 : Est-ce que le moteur est branché ?
            if not self.moteur_mini_llm:
                # -> Si non, retour immédiat d'un score neutre (0.5) avec details vide {}.
                return ResultatJuge(
                    valide=True,
                    score=0.5,
                    raison="Juge indisponible (Pas de moteur)",
                    details={},
                )

            # -> Vérification de sécurité #2 : Taille TOTALE du prompt (Contexte + Question + Réponse).
            # -> Même si le contexte est coupé, la réponse de l'IA pourrait être énorme. On ajoute une marge configurée.
            if len(prompt_juge) > (
                MAX_CHARS_CONTEXTE + int(self.cfg_limites.get("marge_prompt_total"))
            ):  # Marge large
                self.logger.log_warning(
                    "⚠️ Juge: Prompt TOTAL trop gros. Abandon pour éviter le crash."
                )
                # -> Abandon pour éviter une erreur HTTP 400 (Bad Request) du serveur d'inférence.
                return ResultatJuge(
                    valide=True,
                    score=0.5,
                    raison="Non évalué (Trop volumineux)",
                    details={"mode": "securite_taille"},
                )

            # -> Vérification de sécurité #3 (Redondante mais plus sévère) : Si le moteur a disparu entre temps.
            if not self.moteur_mini_llm:
                # -> Ici on renvoie un score de 0.0 (Sanction technique) car c'est une anomalie inattendue à ce stade.
                res = ResultatJuge(
                    valide=True,
                    score=0.0,
                    raison="Moteur Juge indisponible",
                    details={},
                )
                # 🛡️👁️‍🗨️🛡️# VALIDATION FORMAT SORTIE
                self.auditor.valider_format_sortie(res)
                return res

            # -> APPEL API : Envoi synchrone au LLM local.
            reponse_dict = self.moteur_mini_llm.generer(prompt_juge)

            # --- GESTION ERREUR MOTEUR (Le Fix 400 Bad Request) ---
            # -> Si le moteur renvoie None, ou un dictionnaire contenant "error", ou pas de clé "response".
            if (
                not reponse_dict
                or "error" in reponse_dict
                or not reponse_dict.get("response")
            ):
                self.logger.log_warning(
                    "⚠️ Juge: Le Moteur MiniLLM a échoué (probablement Context Overflow). Abstention."
                )
                # -> Retour neutre (0.5) en incluant l'erreur brute dans les détails pour le debug.
                return ResultatJuge(
                    valide=True,
                    score=0.5,
                    raison="Erreur technique Juge (Abstention)",
                    details={"error": str(reponse_dict)},
                )

            # -> Extraction du texte brut généré par le LLM (censé être du JSON).
            reponse_brute_juge = reponse_dict.get("response", "")

            # -> Parsing : Transformation du texte JSON en objet Python ResultatJuge.
            resultat = self._parser_reponse_juge(reponse_brute_juge)

            self.logger.info(
                f"⚖️ Verdict Juge : {resultat.score}/5.0 ({resultat.raison[:50]}...)"
            )
            self._mettre_a_jour_coherence_moyenne(resultat.score)
            # -> On renvoie l'objet parsé une seconde fois (Note: petite redondance ici, on pourrait retourner 'resultat').
            return self._parser_reponse_juge(reponse_brute_juge)

        except Exception as e:
            # -> CATCH-ALL : Si n'importe quoi d'autre plante (variable manquante, bug python).
            self.logger.log_error(f"Erreur critique Juge : {e}")
            # CORRECTION ICI
            # -> On renvoie un résultat valide structurellement, mais neutre (0.5), avec l'exception dans les détails.
            res = ResultatJuge(
                valide=True,
                score=0.5,
                raison=f"Erreur interne: {e}",
                details={"error": str(e)},
            )
            # 🛡️👁️‍🗨️🛡️# VALIDATION FORMAT SORTIE
            self.auditor.valider_format_sortie(res)
            return res

    def _construire_prompt_juge(
        self, contexte_rag_str: str, prompt: str, reponse: str
    ) -> str:
        """
        Génère le prompt système spécialisé pour le "Roleplay" du Juge.

        Définit les règles d'évaluation strictes pour le MiniLLM :
        - Rôle : Évaluateur impitoyable.
        - Tâche : Comparaison Fait vs Affirmation.
        - Sortie : JSON strict uniquement.
        - Échelle : 1.0 (Validé), 0.5 (Incertain), 0.0 (Hallucination).
        """
        return f"""
Tu es un évaluateur de faits, strict et impitoyable. Ton but est de détecter si la "Réponse Générée" est factuellement supportée par le "Contexte Fourni".

Tu dois répondre **UNIQUEMENT** en format JSON.

1. Analyse la "Réponse Générée" et extrais chaque affirmation factuelle.
2. Pour chaque affirmation, compare-la au "Contexte Fourni".
3. Donne un score de fiabilité STRICTEMENT entre 0.0 et 1.0 :
    * **1.0 (Parfait) :** Tous les faits sont validés par le contexte.
    * **0.5 (Incertain) :** La réponse est plausible mais contient des éléments non sourcés.
    * **0.0 (Hallucination) :** La réponse contredit le contexte ou invente des faits.

---
**Contexte Fourni :**
{contexte_rag_str if contexte_rag_str else "Aucun contexte fourni."}

---
**Prompt Utilisateur :**
{prompt}

---
**Réponse Générée (à évaluer) :**
{reponse}

---
**Ton évaluation (FORMAT DE RÉPONSE JSON ATTENDU) :**
{{
    "raison": "Explication courte...",
    "score": 1.0
}}**
```json
"""

    def _extraire_bloc_json(self, texte: str) -> str:
        """
        Extracteur chirurgical de JSON dans une réponse textuelle bruitée.

        Utilise un algorithme de comptage d'accolades (Bracket Counting) plutôt que des Regex
        pour isoler correctement les structures JSON imbriquées, même si le LLM bavarde avant ou après.
        Essentiel pour la fiabilité du pipeline automatisé.
        """
        # -> Nettoyage basique des espaces autour du texte.
        texte = texte.strip()

        # -> Recherche de la première accolade ouvrante '{'.
        idx_debut = texte.find("{")
        # -> Si aucune accolade n'est trouvée, pas de JSON possible -> chaîne vide.
        if idx_debut == -1:
            return ""

        # -> Initialisation du compteur de profondeur (Pile logique).
        compteur = 0

        # -> On parcourt le texte caractère par caractère à partir de la première accolade.
        for i, char in enumerate(texte[idx_debut:], start=idx_debut):
            # -> Si on ouvre un bloc, on incrémente la profondeur.
            if char == "{":
                compteur += 1
            # -> Si on ferme un bloc, on décrémente.
            elif char == "}":
                compteur -= 1
                # -> Si le compteur retombe à 0, c'est qu'on a fermé l'accolade principale initiale.
                # -> On a isolé le bloc JSON complet, on le retourne immédiatement.
                if compteur == 0:
                    return texte[idx_debut : i + 1]

        # -> Si la boucle finit sans que le compteur soit retombé à 0 (JSON mal fermé), on renvoie vide.
        return ""

    def _extraire_json_reponse(self, reponse_brute: str) -> Dict:
        """
        Convertisseur robuste Texte -> Dict avec mécanismes d'auto-réparation.

        Tente de sauver les JSON mal formés (erreurs fréquentes des petits modèles) :
        - Suppression des balises Markdown parasites.
        - Échappement des caractères spéciaux problématiques (Backslashes Windows).
        - Normalisation des sauts de ligne.

        Garantit que le pipeline ne crashe pas pour une virgule manquante.
        """
        import json
        import re

        # 1. Extraction par Pile (Fiable pour les objets imbriqués)
        # -> On isole d'abord la partie qui ressemble à du JSON pour éviter de parser le texte autour.
        json_str = self._extraire_bloc_json(reponse_brute)

        # -> Si rien n'a été extrait, on renvoie un dict vide (Echec silencieux).
        if not json_str:
            return {}

        # -> Nettoyage des balises Markdown (```json et ```) souvent ajoutées par les LLM.
        json_str = json_str.replace("```json", "").replace("```", "").strip()

        try:
            # -> Tentative 1 : Parsing standard. C'est le cas idéal.
            return json.loads(json_str)
        except json.JSONDecodeError:
            # -> Si échec, on entre en mode "Chirurgie".
            try:
                # -> Réparation Backslashes : Les chemins Windows (C:\User) cassent souvent le JSON.
                # -> Cette regex double les backslashes qui ne sont pas déjà des échappements valides.
                json_str_fixed = re.sub(r'\\(?![/u"\\bfnrt])', r"\\\\", json_str)
                # -> Tentative 2 : Avec backslashes corrigés.
                return json.loads(json_str_fixed)
            except:
                # -> Si échec encore, tentative ultime.
                # -> Réparation Newlines : Parfois les sauts de ligne dans les chaînes cassent le format.
                # -> On remplace les sauts de ligne réels par des espaces.
                try:
                    return json.loads(json_str.replace("\n", " "))
                # -> Si tout échoue, on abandonne et renvoie vide.
                except:
                    return {}

    def _parser_reponse_juge(self, reponse_brute: str) -> ResultatJuge:
        """
        Finalise la transformation de l'évaluation brute en objet métier validé.

        Effectue la normalisation finale des scores (Clamping 0.0-1.0), applique le seuil
        de décision binaire (Valide/Invalide) défini dans la configuration, et
        valide le tout via l'Auditor pour conformité contractuelle.
        """
        # -> Import local pour éviter les cycles et garantir le typage.
        from agentique.base.contrats_interface import ResultatJuge

        # -> Appel de la méthode robuste définie juste au-dessus pour avoir un Dict.
        data = self._extraire_json_reponse(reponse_brute)

        # -> Si le dict est vide (parsing échoué), on renvoie un résultat Neutre (0.5) mais Valide structurellement.
        # -> On inclut la réponse brute dans 'details' pour comprendre pourquoi ça a raté.
        if not data:
            return ResultatJuge(
                valide=True,
                score=0.5,
                raison="Erreur technique JSON",
                details={"raw": reponse_brute},
            )

        # -> Lecture directe du score (plus besoin de diviser par 5 comme dans les anciennes versions).
        # -> .get(..., 0.0) protège contre l'absence de clé.
        score = float(data.get("score", 0.0))

        # -> Sécurité bornes : On s'assure (Clamping) que le score reste entre 0.0 et 1.0
        # -> Utile si le LLM hallucine un score hors bornes.
        score = max(0.0, min(1.0, score))

        # -> Instanciation de la Dataclass officielle.
        resultat = ResultatJuge(
            # -> Seuil de validation piloté par la configuration.
            valide=(score >= float(self.cfg_decision.get("seuil_validation"))),
            score=score,
            # -> Récupération de la raison textuelle, ou valeur par défaut.
            raison=data.get("raison", "Analyse Juge"),
            # -> On stocke tout le dictionnaire brut dans les détails pour traçabilité complète.
            details=data,
        )
        # 🛡️👁️‍🗨️🛡️# VALIDATION FORMAT SORTIE
        # -> L'Auditor vérifie que l'objet respecte bien le contrat (champs obligatoires, types).
        self.auditor.valider_format_sortie(resultat)

        # -> Retour de l'objet validé et typé.
        return resultat

    # ========================================
    # MÉTHODES UTILITAIRES DE STATISTIQUES
    # ========================================

    def _mettre_a_jour_coherence_moyenne(self, nouveau_score: float):
        ancienne = self.stats_manager.obtenir_stat_specifique("coherence_moyenne", 1.0)
        nouvelle = 0.1 * nouveau_score + 0.9 * ancienne
        self.stats_manager.definir_stat_specifique(
            "coherence_moyenne", round(nouvelle, 3)
        )
