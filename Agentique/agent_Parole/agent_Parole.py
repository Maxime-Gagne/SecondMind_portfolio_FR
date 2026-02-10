#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AgentParole - Architecte de Prompts Contextuels
Module responsable de la construction finale des instructions (System + User Prompts)
envoyées au Moteur d'Inférence (LLM).

Rôle Architectural :
    L'AgentParole agit comme un "Template Engine" intelligent. Il ne prend aucune décision
    stratégique mais transforme les décisions et données des autres agents (Contexte, Recherche,
    Juge) en une structure textuelle optimisée pour maximiser la performance du modèle.

Responsabilités :
    1. **Assemblage** : Combine les instructions système, le profil utilisateur, les règles actives,
       et les souvenirs récupérés en un prompt unique cohérent.
    2. **Formatage** : Applique les balises de conversation (ChatML: <|im_start|>, etc.) pour
       garantir la séparation stricte entre instructions et données.
    3. **Spécialisation** : Sélectionne le template adéquat selon le mode opératoire
       (Code, Chat, Recherche Web, Cartographie, etc.).
    4. **Injection Dynamique** : Remplace les variables (ex: {profil_utilisateur}) par leur
       valeur en temps réel pour une personnalisation totale.
"""

import yaml
import json
from typing import Union, List, Any
from datetime import datetime

from pathlib import Path
from agentique.base.META_agent import AgentBase
from agentique.base.auditor_base import TrackedDataclass
from agentique.base.contrats_interface import (
    StandardPrompt,
    StandardPromptCode,
    ManualContextCodePrompt,
    NewChatPrompt,
    WebSearchPrompt,
    ProtocolePrompt,
    MemorySearchFirstPrompt,
    MemorySearchPrompt,
    CartographyPrompt,
    FileInspectionPrompt,
    StagingReviewPrompt,
    Souvenir,
    CodeChunk,
    ResultatIntention,
    ModificateursCognitifs,
    SearchMode,
    Sujet,
    Action,
    Categorie,
    Regle,
    DocumentationTechnique,
    FichierReadme,
)


class AgentParole(AgentBase):
    """
    Constructeur de prompts spécialisé et "Stateless".

    Cette classe est purement fonctionnelle : elle prend un objet de requête riche
    (Dataclass contenant toutes les infos contextuelles) et retourne une chaîne de
    caractères (String) prête à être consommée par l'API du LLM.

    Elle garantit que le LLM reçoit toujours :
    - Son identité (System Prompt).
    - Ses contraintes (Règles).
    - Son contexte (Mémoire/Historique).
    - Sa mission immédiate (Prompt User).

    Attributes:
        agent_contexte (AgentContexte): Source de données pour l'historique (optionnel).
        config (Dict): Configuration chargée contenant les templates textuels bruts.
    """

    def __init__(
        self, agent_contexte=None, agent_semi=None, get_cache=None, get_lock=None
    ):
        super().__init__(nom_agent="AgentParole")
        self.agent_contexte = agent_contexte
        self.agent_semi = agent_semi
        self.get_last_prompt_cache = get_cache
        self.get_prompt_lock = get_lock
        self._prompt_callback = None

        # Chargement Config (Source Unique de Vérité pour les textes)
        self.config = self._charger_config()

        self.logger.info("✅ AgentParole (Prompt Builder v2 - Flattened) initialisé.")

    def _charger_config(self) -> dict:
        """Charge la configuration YAML spécifique à AgentParole."""
        path_config = self.auditor.get_path("config")
        if path_config and Path(path_config).exists():
            with open(path_config, "r", encoding="utf-8") as f:
                return yaml.safe_load(f).get("configuration", {})
        return {}

    def _recuperer_profil_utilisateur(self) -> str:
        """Récupère le profil utilisateur brut."""
        root_config = Path(self.auditor.get_path("agent_dir"))
        profil_path = root_config / "profil_utilisateur.md"
        return profil_path.read_text(encoding="utf-8").strip()

    def recuperer_instruction(self, cle: str) -> str:
        """Accesseur public pour que Semi puisse logger/sauvegarder le system prompt utilisé."""
        return self.config.get("prompts", {}).get(cle, "")

    def _recuperer_resume_systeme(self) -> str:
        """Récupère le résumé système brut."""
        dossier_semi = Path(self.auditor.get_path("agent_dir", nom_agent="semi"))
        path = dossier_semi / "etat_systeme_resume.md"
        return path.read_text(encoding="utf-8").strip()

    def _formater_system_prompt(self, template: str) -> str:
        """
        Injecte les variables. FAIL FAST : Si instructions_outils manque, on crashe.
        """
        # 1. Récupération sécurisée du chemin
        chemin_outils = (
            Path(self.auditor.get_path("agent_dir")) / "instructions_outils.md"
        )

        # 2. FAIL FAST : Vérification explicite
        if not chemin_outils.exists():
            # On logge pour la trace
            self.logger.log_error(f"❌ CRITIQUE : {chemin_outils} introuvable.")
            # On laisse planter (ou on lève manuellement) pour stopper l'agent
            raise FileNotFoundError(f"Fichier critique manquant : {chemin_outils}")

        # 3. Lecture propre (Style pathlib)
        txt_outils = chemin_outils.read_text(encoding="utf-8").strip()

        variables = {
            "contenu_actuel_resume": self._recuperer_resume_systeme(),
            "profil_utilisateur": self._recuperer_profil_utilisateur(),
            "instructions_outils": txt_outils,  # Plus de risque de vide ici
        }

        try:
            # On tente le formatage propre
            return template.format(**variables)
        except KeyError:
            # Si le template ne contient pas les clés (vieux yaml), on concatène brutalement
            out = template
            if "{profil_utilisateur}" not in template:
                out += (
                    f"\n\n### 👤 PROFIL UTILISATEUR\n{variables['profil_utilisateur']}"
                )
            if "{contenu_actuel_resume}" not in template:
                out += f"\n\n### 🛡️ RÉSUMÉ SYSTÈME\n{variables['contenu_actuel_resume']}"
            if "{instructions_outils}" not in template:
                out += f"\n\n### ⚙️ UTILISATION DES OUTILS\n{variables['instructions_outils']}"
            return out
        except Exception as e:
            self.logger.log_warning(f"Erreur formatage system prompt: {e}")
            return template

    # =========================================================================
    # AIGUILLEUR PRINCIPAL
    # =========================================================================

    def construire_prompt_llm(
        self,
        req: Union[
            StandardPrompt,
            StandardPromptCode,
            ManualContextCodePrompt,
            WebSearchPrompt,
            ProtocolePrompt,
            CartographyPrompt,
            FileInspectionPrompt,
            StagingReviewPrompt,
        ],
    ) -> str:
        """
        Point d'entrée unique pour la génération de prompt (Dispatcher).

        Analyse le type de la Dataclass fournie en entrée pour diriger le flux
        vers la méthode de construction spécialisée appropriée (Pattern Visitor).

        Gère également :
        - La validation des entrées (Non-Nullité).
        - L'audit des champs utilisés (via TrackedDataclass).
        - La mise à jour du cache pour le "Prompt Viewer" (Outil de debug).

        Args:
            req (Dataclass): L'objet requête contenant toutes les données nécessaires.

        Returns:
            str: Le prompt complet formaté, incluant les balises spéciales.
        """

        # 🛡️👁️‍🗨️🛡️# VALIDATION FORMAT ENTREE
        if req is None:
            raise ValueError("❌ Semi n'a pas fourni de prompt_obj à Parole")

        from dataclasses import is_dataclass

        if not is_dataclass(req):
            raise TypeError(
                f"❌ Parole doit recevoir une dataclass, reçu: {type(req).__name__}"
            )

        # Wrapper pour tracking
        tracked_obj = TrackedDataclass(req)

        # ⚠️ IMPORTANT : isinstance() doit tester req, PAS tracked_obj
        # Construction du prompt
        if isinstance(req, StandardPromptCode):
            prompt_final = self._construire_prompt_code(tracked_obj)
        elif isinstance(req, StandardPrompt):
            prompt_final = self._construire_prompt_standard(tracked_obj)
        elif isinstance(req, ManualContextCodePrompt):
            prompt_final = self._construire_prompt_contexte_manuel(tracked_obj)
        elif isinstance(req, MemorySearchFirstPrompt):  # <--- NOUVEAU
            prompt_final = self._construire_memory_search_first_prompt(tracked_obj)
        elif isinstance(req, MemorySearchPrompt):
            prompt_final = self._construire_prompt_memory_search(tracked_obj)
        elif isinstance(req, CartographyPrompt):
            prompt_final = self._construire_prompt_cartography(tracked_obj)
        elif isinstance(req, FileInspectionPrompt):
            prompt_final = self._construire_prompt_inspection(tracked_obj)
        elif isinstance(req, StagingReviewPrompt):
            prompt_final = self._construire_prompt_review(tracked_obj)
        elif isinstance(req, WebSearchPrompt):
            prompt_final = self._construire_prompt_web_search(tracked_obj)
        elif isinstance(req, ProtocolePrompt):
            prompt_final = self._construire_prompt_protocole(tracked_obj)
        else:
            raise TypeError(f"Type de dataclass inconnu: {type(req).__name__}")

        # 🛡️👁️‍🗨️🛡️# VALIDATION FORMAT SORTIE
        if prompt_final is None or not isinstance(prompt_final, str):
            raise RuntimeError(
                f"❌ La méthode de construction a retourné {type(prompt_final)} au lieu de str"
            )

        # Validation des champs utilisés
        succes_audit = self.auditor.valider_utilisation_complete(tracked_obj)

        if not succes_audit:
            # On ne crash pas pour les nouveaux prompts en phase de dev, mais on log fortement
            self.logger.log_warning(
                f"❌ ALERTE PAROLE : Champs ignorés dans {type(req).__name__}. Vérifiez les logs Auditor."
            )

        # ✨ AJOUT : INJECTION DU MARQUEUR DE TYPE (POUR LE VIEWER)
        # On ajoute une ligne spéciale au tout début pour le parsing HTML
        prompt_final = f"#! PROMPT_TYPE: {type(req).__name__}\n" + prompt_final

        self._update_viewer(prompt_final, type(req).__name__)
        return prompt_final

    # =========================================================================
    # CONSTRUCTEURS STRICTS (JSON-SAFE)
    # =========================================================================

    def _construire_prompt_standard(self, req: StandardPrompt) -> str:
        """
        Génère un prompt pour une interaction conversationnelle classique.

        Structure du Prompt :
        1. **System** : Identité de base + Profil Utilisateur.
        2. **User** :
           - Intention détectée (Sujet/Action).
           - Documentation pertinente (READMEs).
           - Règles de gouvernance actives.
           - Contexte mémoriel (RAG).
           - Historique récent.
           - Question actuelle.

        Args:
            req (StandardPrompt): Données pour le chat standard.

        Returns:
            str: Prompt ChatML.
        """
        txt_systeme = self._formater_system_prompt(req.instructions_systeme)

        return (
            f"<|im_start|>system\n{txt_systeme}\n<|im_end|>\n"
            f"<|im_start|>user\n"
            f"### INTENTION DÉTECTÉE\n"
            f"Sujet: {req.intention.sujet} | Action: {req.intention.action} | Catégorie: {req.intention.categorie}\n"
            f"---\n"
            f"{self._formater_fichiers_readme(req.fichiers_readme)}"
            f"{self._formater_regles(req.regles)}"
            f"{self._formater_contexte_memoire(req.contexte_memoire)}"
            f"{self._formater_historique(req.historique)}"
            f"\n### QUESTION ACTUELLE\n{req.prompt_original}"
            f"<|im_end|>\n<|im_start|>assistant\n"
        )

    def _construire_prompt_code(self, req: StandardPromptCode) -> str:
        """
        Génère un prompt optimisé pour les tâches de génération/analyse de code.

        Différences clés avec le prompt standard :
        - System Prompt orienté "Expert Technique".
        - Injection de "Code Chunks" (Snippets vectoriels) pour donner du contexte technique.
        - Priorisation des règles de style et de syntaxe.

        Args:
            req (StandardPromptCode): Données spécifiques au coding.
        """
        txt_systeme = req.instructions_code_prompt.replace(
            "{profil_utilisateur}", self._recuperer_profil_utilisateur()
        )

        return (
            f"<|im_start|>system\n{txt_systeme}\n<|im_end|>\n"
            f"<|im_start|>user\n"
            f"### INTENTION DÉTECTÉE\n"
            f"Sujet: {req.intention.sujet} | Action: {req.intention.action} | Catégorie: {req.intention.categorie}\n"
            f"---\n"
            f"{self._formater_code_chunks(req.code_chunks)}"
            f"{self._formater_fichiers_readme(req.fichiers_readme)}"
            f"{self._formater_regles(req.regles)}"
            f"{self._formater_historique(req.historique)}"
            f"\n### DEMANDE TECHNIQUE\n{req.prompt_original}\n\n"
            f"<|im_end|>\n<|im_start|>assistant\n"
        )

    def _construire_prompt_contexte_manuel(self, req: ManualContextCodePrompt) -> str:
        txt_systeme = req.instructions_contexte_manuel.replace(
            "{profil_utilisateur}", self._recuperer_profil_utilisateur()
        )

        return (
            f"<|im_start|>system\n{txt_systeme}\n<|im_end|>\n"
            f"<|im_start|>user\n"
            f"### INTENTION DÉTECTÉE\n"
            f"Sujet: {req.intention.sujet} | Action: {req.intention.action} | Catégorie: {req.intention.categorie}\n"
            f"---\n"
            f"### 📁 CODE MANUEL (SOURCE DE VÉRITÉ)\n"
            f"```python\n{req.contexte_manuel}\n```\n"
            f"--------------------------------------------------\n"
            f"{self._formater_fichiers_readme(req.fichiers_readme)}"
            f"{self._formater_regles(req.regles)}"
            f"{self._formater_historique(req.historique)}"
            f"\n### CONSIGNE SUR LE CODE\n{req.prompt_original}"
            f"<|im_end|>\n<|im_start|>assistant\n"
        )

    def _construire_memory_search_first_prompt(
        self, req: MemorySearchFirstPrompt
    ) -> str:
        """
        Prompt d'initialisation pour le mode "Recherche Profonde".

        Appelé quand le système décide d'investiguer AVANT de répondre.
        Met l'accent sur la définition d'un plan de recherche basé sur les premiers
        indices mémoriels disponibles.
        """
        return (
            f"<|im_start|>system\n"
            f"{req.instructions_first_search.format(prompt_original=req.prompt_original, resultats_memoire=self._formater_contexte_memoire(req.resultats_memoire))}\n"
            f"<|im_end|>\n"
            f"<|im_start|>user\n"
            f"### INTENTION DÉTECTÉE\n"
            f"Sujet: {req.intention.sujet.value} | Action: {req.intention.action.value}\n"
            f"--------------------------------------------------\n"
            f"C'est le début de l'investigation. Construis le plan d'attaque.\n"
            f"<|im_end|>\n<|im_start|>assistant\n"
        )

    def _construire_prompt_memory_search(self, req: MemorySearchPrompt) -> str:
        return (
            f"<|im_start|>system\n"
            f"{req.instructions_memory_search_prompt.format(prompt_original=req.prompt_original, raisonnement_precedent=req.raisonnement_precedent)}\n"
            f"<|im_end|>\n"
            f"<|im_start|>user\n"
            f"### INTENTION\n"
            f"Sujet: {req.intention.sujet.value} | Action: {req.intention.action.value}\n"
            f"--------------------------------------------------\n"
            f"### 📂 RÉSULTATS\n"
            f"{self._formater_contexte_memoire(req.resultats_memoire)}\n"
            f"### ⚡ PHASE DE DÉCISION (RAPPEL CRITIQUE)\n"
            f"Tu viens de lire les resultats_memoire ci-dessus.\n"
            f"Compare-les avec ton raisonnement_precedent.\n"
            f"Si tu as TOUT pour répondre à prompt_original -> Utilise `final_answer`.\n"
            f"Sinon -> `lire_fichier` ou `rechercher_memoire`.\n"
            f"<|im_end|>\n<|im_start|>assistant\n"
        )

    def _construire_prompt_cartography(self, req: CartographyPrompt) -> str:
        """
        Prompt pour le mode "Navigation Autonome" (Exploration de Codebase).

        Fournit au LLM :
        1. La "Map" complète du projet (arborescence fichiers).
        2. Le "Plan de Bataille" (fichiers déjà visités vs à visiter).
        3. L'objectif final.

        Force le modèle à choisir le PROCHAIN fichier à inspecter, transformant
        le LLM en agent de parcours de graphe.
        """
        return (
            f"<|im_start|>system\n{req.instructions_cartographie}\n<|im_end|>\n"
            f"<|im_start|>user\n"
            f"### INTENTION (GUIDAGE)\n"
            f"Sujet: {req.intention.sujet} | Action: {req.intention.action} | Catégorie: {req.intention.categorie}\n"
            f"--------------------------------------------------\n"
            f"### 🗺️ CARTOGRAPHIE DU PROJET (VUE HÉLICOPTÈRE)\n"
            f"{req.cartographie_projet}\n\n"
            f"--------------------------------------------------\n"
            f"### 📋 PLAN DE BATAILLE ACTUEL\n"
            f"{self._formater_liste_simple(req.plan_de_bataille)}\n\n"
            f"--------------------------------------------------\n"
            f"### MISSION EN COURS\n"
            f"{req.prompt_original}\n\n"
            f"👉 DÉCISION REQUISE : Quel est le PROCHAIN fichier unique à inspecter ?\n"
            f"Réponds par un tool call `lire_fichier` ou `final_answer`."
            f"<|im_end|>\n<|im_start|>assistant\n"
        )

    def _construire_prompt_inspection(self, req: FileInspectionPrompt) -> str:
        return (
            f"<|im_start|>system\n{req.instructions_inspection}\n<|im_end|>\n"
            f"<|im_start|>user\n"
            f"### INTENTION (GUIDAGE)\n"
            f"Sujet: {req.intention.sujet} | Action: {req.intention.action} | Catégorie: {req.intention.categorie}\n"
            f"--------------------------------------------------\n"
            f"### 🔧 SUR L'ÉTABLI : {req.fichier_en_cours.titre}\n"
            f"{req.fichier_en_cours.contenu}\n\n"
            f"--------------------------------------------------\n"
            f"### 📝 NOTES DE CONTEXTE (POURQUOI CE FICHIER ?)\n"
            f"{req.notes_precedentes}\n\n"
            f"--------------------------------------------------\n"
            f"### TÂCHE D'INSPECTION\n"
            f"1. Analyse ce fichier par rapport à la demande : '{req.prompt_original}'.\n"
            f"2. Si des modifications sont nécessaires, utilise `update_system_summary` pour les noter dans le STAGING.\n"
            f"3. Si tout est OK, passe au suivant ou termine.\n"
            f"<|im_end|>\n<|im_start|>assistant\n"
        )

    def _construire_prompt_review(self, req: StagingReviewPrompt) -> str:
        return (
            f"<|im_start|>system\n{req.instructions_review}\n<|im_end|>\n"
            f"<|im_start|>user\n"
            f"### INTENTION (GUIDAGE)\n"
            f"Sujet: {req.intention.sujet} | Action: {req.intention.action} | Catégorie: {req.intention.categorie}\n"
            f"--------------------------------------------------\n"
            f"### ✅ DERNIÈRE ACTION EFFECTUÉE\n"
            f"{req.derniere_action}\n\n"
            f"--------------------------------------------------\n"
            f"### 🚧 ÉTAT ACTUEL DU STAGING (RÉSUMÉ SYSTÈME)\n"
            f"{req.etat_staging_actuel}\n\n"
            f"--------------------------------------------------\n"
            f"### DÉCISION DE PILOTAGE\n"
            f"Le travail sur ce fichier est terminé.\n"
            f"- Veux-tu retourner à la carte pour un autre fichier ? -> `rechercher_memoire(query='lire_cartographie')`\n"
            f"- Veux-tu terminer la session d'autonomie ? -> `final_answer`\n"
            f"<|im_end|>\n<|im_start|>assistant\n"
        )

    def _construire_prompt_web_search(self, req: WebSearchPrompt) -> str:
        source_txt = "\n".join(
            [f"- {r.get('title')}: {r.get('snippet')}" for r in req.resultats_web]
        )

        return (
            f"<|im_start|>system\n{req.instructions_web_search_prompt}\n<|im_end|>\n"
            f"<|im_start|>user\n"
            f"Sources:\n{source_txt}\n\nQuestion: {req.query}"
            f"<|im_end|>\n<|im_start|>assistant\n"
        )

    def _construire_prompt_protocole(self, req: ProtocolePrompt) -> str:
        return (
            f"<|im_start|>system\n{req.protocole_contenu}\n<|im_end|>\n"
            f"<|im_start|>user\n"
            f"### CONTEXTE IMMÉDIAT (10 derniers messages)\n"
            f"{self._formater_historique(req.historique_recent)}\n"
            f"---\n"
            f"### SIGNAL D'ALERTE UTILISATEUR\n"
            f"{req.prompt_original}\n\n"
            f"Applique le protocole d'intervention maintenant."
            f"<|im_end|>\n<|im_start|>assistant\n"
        )

    def prompt_premier_chat(self, prompt_original: str) -> str:
        """
        Génère le prompt spécial d'initialisation de session (Cold Start).

        Contrairement aux autres prompts qui dépendent d'un contexte riche,
        celui-ci doit être robuste même sans historique. Il injecte massivement
        le "Résumé Système" pour donner à l'agent une conscience immédiate de son état.

        Args:
            prompt_original (str): Le tout premier message de l'utilisateur.
        """
        req = NewChatPrompt(
            prompt_original=prompt_original,
            instructions_premier_prompt=self.recuperer_instruction(
                "instructions_premier_prompt"
            ),
            modificateurs=ModificateursCognitifs(search_mode=SearchMode.NONE),
            intention=ResultatIntention(
                prompt=prompt_original,
                sujet=Sujet.SECONDMIND,
                action=Action.PARLER,
                categorie=Categorie.SALUER,
            ),
            dernier_historique_chat=self.agent_contexte.get_historique_nouveau_chat()
            if self.agent_contexte
            else [],
            resume_systeme=self._recuperer_resume_systeme(),
        )

        # Utilisation de .replace() pour la robustesse
        txt_systeme = req.instructions_premier_prompt.replace(
            "{profil_utilisateur}", self._recuperer_profil_utilisateur()
        )

        prompt_final = (
            f"<|im_start|>system\n{txt_systeme}\n<|im_end|>\n"
            f"<|im_start|>user\n"
            f"------------------------------------------------------------\n"
            f"### RÉSUMÉ DU SYSTÈME\n{req.resume_systeme}\n"
            f"------------------------------------------------------------\n"
            f"### ⚠️ CONTEXTE PRÉCÉDENT (POUR CONTINUITÉ)\n"
            f"{self._formater_historique(req.dernier_historique_chat)}"
            f"\n### PREMIER MESSAGE UTILISATEUR\n{req.prompt_original}"
            f"<|im_end|>\n<|im_start|>assistant\n"
        )

        self._update_viewer(prompt_final, "NewChatPrompt")
        return prompt_final

    # ---------------------------------------------------------
    # MISE À JOUR DU CACHE (PROMPT VIEWER)
    # ---------------------------------------------------------
    def _update_viewer(self, prompt_str, type_req):
        """Mise à jour du cache pour le Prompt Viewer"""
        if self._prompt_callback:
            try:
                cache = self.get_last_prompt_cache()
                lock = self.get_prompt_lock()
                with lock:
                    cache["raw_prompt"] = prompt_str
                    cache["timestamp"] = datetime.now().isoformat()
                    cache["prompt_type"] = type_req
                self._prompt_callback(prompt_str)
            except Exception:
                pass

    # =========================================================================
    # 📐 FORMATEURS DE SECTIONS
    # =========================================================================

    def _formater_fichiers_readme(self, docs):
        """
        Injecte la doc (FichierReadme ou DocumentationTechnique).
        Compatible avec les deux types car ils ont tous deux 'titre' et 'contenu'.
        """
        if not docs:
            return ""

        out = "\n### 📚 fichiers_readme\n"
        out += "Voici les références pour t'assurer de respecter les standards.\n\n"

        for doc in docs:
            # Gestion polymorphe
            titre = doc.titre
            contenu = doc.contenu

            # Info extra si disponible (ex: chemin ou url)
            info_sup = ""
            if hasattr(doc, "chemin") and doc.chemin:
                info_sup = f" ({doc.chemin})"
            elif hasattr(doc, "source_url") and doc.source_url:
                info_sup = f" (Source: {doc.source_url})"

            out += f"**{titre}**{info_sup}\n{contenu}\n\n"

        return out + "--------------------------------------------------\n"

    def _formater_regles(self, regles):
        """
        Injecte les règles avec l'objectif de contrainte.
        """
        if not regles:
            return ""

        out = "\n### ⚖️ RÈGLES & GOUVERNANCE\n"
        out += "Voici les contraintes strictes que tu dois respecter pour cette interaction.\n\n"

        for regle in regles:
            txt = regle.contenu if hasattr(regle, "contenu") else str(regle)
            prefix = (
                "🚨 ALERTE" if "ALERTE" in getattr(regle, "titre", "") else "⚠️ Règle"
            )
            out += f"{prefix} : {txt}\n"

        return out + "--------------------------------------------------\n"

    def _formater_contexte_memoire(self, souvenirs: List[Souvenir]) -> str:
        """
        Transforme une liste d'objets 'Souvenir' en bloc texte lisible.

        Fonction critique pour le RAG. Elle :
        1. Filtre les souvenirs vides ou non pertinents.
        2. Tente de parser le contenu JSON pour un affichage structuré (Q/R).
        3. Ajoute des avertissements ("Ce sont des résumés") pour limiter les hallucinations.

        Args:
            souvenirs (List[Souvenir]): Résultats bruts de la recherche vectorielle.

        Returns:
            str: Section formatée prête à être injectée dans le prompt.
        """
        if not souvenirs:
            raise ValueError(
                "❌ _formater_contexte_memoire: Liste de souvenirs vide - données obligatoires manquantes!"
            )

        out = (
            "\n CONTEXTE MÉMOIRE (POINTEURS & RÉSUMÉS)\n"
            "⚠️ NOTE TECHNIQUE : Les éléments ci-dessous proviennent de la mémoire à long terme (Vectorielle).\n"
            "Ce sont souvent des RÉSUMÉS synthétiques ('Demande sur...').\n"
            "ILS PROUVENT QUE LA DISCUSSION A EU LIEU, MAIS NE CONTIENNENT PAS LES DÉTAILS.\n"
            "👉 DIRECTIVE : Si l'utilisateur demande de 'rappeler' ou 'résumer' cette discussion précise :\n"
            "1. NE DIS PAS que tu ne t'en souviens pas.\n"
            "2. UTILISE l'outil `rechercher_memoire` pour trouver le transcript brut dans l'historique.\n"
            "--------------------------------------------------------------\n"
        )
        # Limite stricte à 6 éléments
        selection = souvenirs[:6]

        for i, souv in enumerate(selection, 1):
            score = getattr(souv, "score", 0.0)
            contenu_str = souv.contenu

            # Cas spécial : Message vide explicite
            if contenu_str == "aucun contexte jugé pertinent":
                out += f"ℹ️ {contenu_str}\n"
                continue

            # Essai de parsing JSON pour affichage structuré
            try:
                data = json.loads(contenu_str)
                # Si c'est un dictionnaire valide (Interaction sauvegardée)
                prompt = data.get("prompt", "N/A")
                reponse = data.get("reponse", "N/A")
                ts = data.get("timestamp", "N/A")

                out += (
                    f"--- Souvenir #{i} (Score: {score:.2f}) ---\n"
                    f"Timestamp: {ts}\n"
                    f"PROMPT: {prompt}...\n"
                    f"RÉPONSE: {reponse}...\n"
                )
            except (json.JSONDecodeError, AttributeError):
                out += f"--- Souvenir #{i} (Score: {score:.2f}) ---\n{contenu_str}...\n"

        return out + "--------------------------------------------------------------\n"

    def _formater_historique(self, historique: List[str]) -> str:
        """
        Injecte l'historique avec l'objectif de continuité.
        """
        if not historique:
            return ""

        out = "\n### 🕰️ HISTORIQUE DE CONVERSATION\n"
        out += "Voici les derniers échanges ci-dessous, à titre de référence pour t'aider à garder le fil de la conversation.\n\n"

        # Logique de formatage existante (User/Assistant)
        msgs = [m.get("content", "") if isinstance(m, dict) else m for m in historique]
        for i in range(0, len(msgs), 2):
            if i + 1 < len(msgs):
                out += f"👤 Utilisateur : {msgs[i]}\n🤖 Assistant : {msgs[i + 1]}\n"

        return out + "--------------------------------------------------------------\n"

    def _formater_code_chunks(self, chunks: List[CodeChunk]) -> str:
        """
        Injecte les snippets avec une consigne claire sur leur usage.
        """
        if not chunks:
            return ""

        out = "\n### 🧩 EXTRAITS DE CODE (POUR CONTEXTE GLOBAL)\n"
        out += "Voici des fragments issus de la mémoire vectorielle pour t'aider à situer le code.\n"
        out += "⚠️ ATTENTION : Ce ne sont que des aperçus. Pour modifier ou auditer, utilise D'ABORD `lire_fichier` pour avoir la version complète.\n\n"

        for c in chunks:
            # On garde l'info du chemin propre
            out += f"--- Fichier suggéré : {c.chemin} ---\n"
            out += f"```{c.langage}\n{c.contenu}\n```\n\n"

        return out + "--------------------------------------------------------------\n"

        # Nouvelle méthode de formatage

    def _formater_code(self, code_items: List[Any]) -> str:
        """En-tête CONTEXTE CODE"""
        if not code_items:
            return ""

        out = "\n### CONTEXTE TECHNIQUE (CODE SOURCE)\n"
        for item in code_items:
            txt = item.contenu if hasattr(item, "contenu") else str(item)
            out += f"{txt}\n"
        return (
            out
            + "----------------------------------------------------------------------\n"
        )
