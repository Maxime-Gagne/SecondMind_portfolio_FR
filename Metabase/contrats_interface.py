#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Règles SecondMind:
Les agents importent leur managers et modules externes,
Semi importe tout le monde et injecte les dépendances.
Les agents ne s'importent pas entre eux

CONTRATS D'INTERFACE STANDARDISÉS - VERSION FINALE
=================================================
Ce fichier est la source de vérité absolue pour le vocabulaire
et les structures de données de l'ensemble du système.

RÈGLES :
1. Ce fichier est la référence unique pour les Enums et les Dataclasses.
2. Toute communication inter-agents DOIT utiliser ces contrats.
3. Ce contrat est la référence pour les objets de données échangés entre les agents.
"""
import json
import uuid
from dataclasses import dataclass, field, fields
from typing import Dict, List, Any, Optional
from dataclasses import asdict, is_dataclass
from pydantic import BaseModel, Field, validator
from pathlib import Path
from datetime import datetime
from enum import Enum
import unicodedata
from enum import Enum
from agentique.base.utils_text import EnumFlexible
# Cette classe sert juste de "traducteur". Elle ne change pas les données.
class FlexibleEnum(Enum):
    @classmethod
    def _missing_(cls, value):
        # Si la valeur exacte n'est pas trouvée, on essaie de normaliser
        if isinstance(value, str):
            def clean(text):
                # Enlève les accents et met en minuscule
                return "".join(c for c in unicodedata.normalize('NFD', text)
                             if unicodedata.category(c) != 'Mn').lower().strip()

            valeur_cherchee = clean(value)

            # On compare avec toutes les options existantes
            for member in cls:
                if clean(member.value) == valeur_cherchee:
                    return member
        return None
# ========================================
# 1. ÉNUMÉRATIONS (Le Vocabulaire Strict)
# ========================================
@dataclass
class Sujet(EnumFlexible):
    SECONDMIND = "SecondMind" #tout ce qui concerne mon système IA en général
    SETUP = "Setup" #tout ce qui est installation/matériel/configuration
    SCRIPT = "Script" #tout ce qui est du code python ou .yaml
    FICHIER = "Fichier"#tout ce qui est du fichier non code (.txt, README, .md, .pdf, etc)
    GENERAL = "Général" #tout ce qui ne concerne pas mon système IA`

class Action(EnumFlexible):
    FAIRE = "Faire"
    PENSER = "Penser"
    PARLER = "Parler"
    CODER = "Coder"
    DEBUG = "Debug"


class Categorie(EnumFlexible):
    PLANIFIER = "Planifier"
    TESTER = "Tester"
    CONFIGURER = "Configurer"
    DOCUMENTER = "Documenter"
    ANALYSER = "Analyser"
    DEFINIR = "Définir"
    COMPARER = "Comparer"
    DEMANDER = "Demander"
    CONFIRMER = "Confirmer"
    SALUER = "Saluer"
    #Catégories pour CODER & DEBUG
    AGENT = "Agent"
    SYSTEME = "Système" #tout script ou fichier de mon système IA mais qui n'est pas un agent
    BACKEND = "Backend" #tout ce qui concerne le backend (serveur, API, DB, etc)
    TEST = "Test"
    AUTRE = "Autre"

class TypeMemoire(Enum):
    """Types de mémoire"""
    TRAVAIL = "travail"
    HISTORIQUE = "historique"
    REFLEXIVE = "reflexive"
    REGLES = "regles"
    FEEDBACK = "feedback"
    BRUTE = "brute"
    PERSISTANTE = "persistante"
    CONNAISSANCES = "connaissances"
    VECTORIELLE = "vectorielle"
    TEMP = "temp"
    MODULES_FORMATIONS = "modules_formations"

class SearchMode(Enum):
    """
    Modes de recherche pilotés EXCLUSIVEMENT par l'interface frontend.
    L'IA n'a pas le droit d'initier une recherche d'elle-même.
    """
    NONE = "none"               # Par défaut : Aucune recherche externe
    WEB = "web"                 # Force la recherche Web
    CONTEXTE_MANUEL = "manual_context"  # Force l'utilisation des Slots manuels

# ========================================
# 2. UTILITAIRES JSON
# ========================================

class CustomJSONEncoder(json.JSONEncoder):
    """Encodeur universel pour Dataclasses et Enums."""
    def default(self, o):
        if is_dataclass(o): return asdict(o)
        if isinstance(o, Enum): return o.value
        if isinstance(o, Path): return str(o)
        if isinstance(o, datetime): return o.isoformat()
        return super().default(o)

# ========================================
# 3. LES MÉTADONNÉES STANDARDISÉES
# ========================================
""""
Comment AgentSemi gère ça ?

Voici la logique simple que Semi appliquera :

Début :
Création de meta_fichier = MetadataFichier(...)
Création de meta_pipeline = MetadataPipeline(...)

Exécution :
Semi remplit meta_pipeline au fur et à mesure (temps, tokens).
Semi remplit meta_fichier avec les infos contextuelles (fichiers trouvés).

Fin :
Sauvegarde : Semi enregistre l'objet Interaction (qui contient meta_fichier).
Logging : Semi envoie meta_pipeline à son Logger :
logger.info(f"Pipeline terminé en {meta_pipeline.temps_total}s. Tokens: {meta_pipeline.nb_tokens_sortie}")"
"""

@dataclass
class MetadataFichier:
    """
    PERSISTANT : Infos contextuelles conservées dans l'ARCHIVE.
    Contient TOUT ce qui n'est pas le texte de la conversation.
    """
    # --- IDENTITÉ & SESSION ---
    id: str = field(default_factory=lambda: str(uuid.uuid4())) # anc. id_unique
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat()) # anc. timestamp_utc
    session_id: Optional[str] = None
    message_turn: Optional[int] = None  # ✅ RAJOUTÉ
    source_agent: str = "Semi"
    type_memoire: str = "historique"    # ✅ RAJOUTÉ (anc. Enum TypeMemoire)

    # Traçabilité
    fichiers_consultes: List[str] = field(default_factory=list)

    # --- QUALITÉ (JUGE) ---
    validation_juge: bool = False
    score_qualite: float = 0.0          # anc. score_coherence
    nb_problemes: int = 0               # ✅ RAJOUTÉ
    details_juge: Optional[str] = None  # ✅ RAJOUTÉ (anc. evaluation_juge_details)

    # --- INDEXATION TECHNIQUE ---
    len_contenu: int = 0                # ✅ RAJOUTÉ
    ref_vectoriel: Optional[int] = None # ✅ RAJOUTÉ (anc. index_vectoriel_id)
    ref_whoosh: Optional[str] = None    # ✅ RAJOUTÉ (anc. index_whoosh_path)

    # --- EXTENSION ---
    data_libre: Dict[str, Any] = field(default_factory=dict) # ✅ RAJOUTÉ (anc. metadata_libre)

@dataclass
class MetadataPipeline:
    """
    VOLATILE : Infos de performance et de debug.
    Envoyé dans les logs de Semi, ne pollue pas la mémoire long terme.
    """
    # --- IDENTITÉ & SESSION ---
    interaction_id: str
    # Chronométrage
    temps_total: float = 0.0
    temps_intention: float = 0.0
    temps_recherche: float = 0.0
    temps_generation: float = 0.0

    # Détails techniques
    modele_utilisé: str = ""
    nb_tokens_entree: int = 0
    nb_tokens_sortie: int = 0
    succes: bool = True
    erreur: Optional[str] = None

# ========================================
# 3. LES ATOMES (Briques élémentaires)
# ========================================

@dataclass
class Souvenir:
    """
    ATOME 2 : Sortie unifiée de l'AgentRecherche.
    Le plus petit dénominateur commun de la mémoire.
    """
    contenu: str        # Le texte brut à lire
    titre: str          # Identifiant
    type: str
    score: float  # Pertinence (1.0 = Max/Forcé)

@dataclass
class Regle:
    """ATOME RÈGLE : Uniquement pour la gouvernance."""
    contenu: str
    titre: str          # ID de la règle (ex: R01)
    type: str = "regle" # Fixe
    score: float = 10.0 # Toujours prioritaire

@dataclass
class FichierReadme:
    """ATOME : Documentation INTERNE du projet (README.md, specs locales)."""
    contenu: str
    titre: str
    chemin: str = "" # Utile pour savoir où il est dans le projet
    type: str = "readme"
    score: float = 1.0

@dataclass
class DocumentationTechnique:
    """ATOME : Documentation EXTERNE (Librairies, API, Web Scraping)."""
    contenu: str
    titre: str
    source_url: str = "" # Utile pour citer la source externe
    type: str = "doc_technique"
    score: float = 1.0

@dataclass
class ModificateursCognitifs:
    """
    ATOME 3 : Configuration venant de l'UI
    """
    search_mode: SearchMode
    activer_cot: bool = False
    enable_thinking: bool = False

# ========================================
# 4. FORMATS DE SORTIE PAR AGENT (Le Cœur du Système)
# ========================================

@dataclass
class ResultatIntention:
    """
    SORTIE DE : IntentionDetector
    Ce qu'il rend au système après analyse.
    """
    prompt: str           # Le signal d'origine (transporté)
    sujet: Sujet
    action: Action
    categorie: Categorie

    def __post_init__(self):
        if not self.prompt:
            raise ValueError("❌ ResultatIntention: prompt vide - données obligatoires manquantes!")
        if not isinstance(self.sujet, Sujet):
            raise TypeError(f"❌ ResultatIntention: sujet doit être un Sujet, reçu {type(self.sujet)}")
        if not isinstance(self.action, Action):
            raise TypeError(f"❌ ResultatIntention: action doit être une Action, reçu {type(self.action)}")
        if not isinstance(self.categorie, Categorie):
            raise TypeError(f"❌ ResultatIntention: categorie doit être une Categorie, reçu {type(self.categorie)}")

@dataclass
class ResultatRecherche:
    """
    SORTIE DE : AgentRecherche
    """
    souvenirs_bruts: List[Souvenir] # ✅ Autorise maintenant la liste vide []
    nb_fichiers_scannes: int = 0
    temps_recherche: float = 0.0

    def __post_init__(self):
        # La validation stricte 'if not self.souvenirs_bruts' est retirée
        if self.nb_fichiers_scannes < 0:
            raise ValueError(f"❌ ResultatRecherche: nb_fichiers_scannes invalide ({self.nb_fichiers_scannes})")
        if self.temps_recherche < 0:
            raise ValueError(f"❌ ResultatRecherche: temps_recherche invalide ({self.temps_recherche})")
@dataclass
class ResultatRechercheWeb:
    url: str
    titre: str
    contenu_complet: str  # Le texte scrapé (gros volume)
    resume_pertinent: str # Ce que l'agent a extrait d'utile
    score_pertinence: int # 0-10

@dataclass
class ResultatContexte:
    """
    SORTIE DE : AgentContexte
    Typage strict pour validation Auditor.
    """
    contexte_memoire: List[Souvenir]       # Mémoire pure
    regles_actives: List[Regle]             # <--- Typage strict
    historique: List[str]
    fichiers_readme: List[FichierReadme]
    intention_detectee: ResultatIntention
    def __post_init__(self):
        if not self.contexte_memoire:
            raise ValueError("❌ ResultatContexte: contexte_memoire vide - données obligatoires manquantes!")
        if not self.regles_actives:
            raise ValueError("❌ ResultatContexte: regles_actives vide - données obligatoires manquantes!")
        if not self.fichiers_readme:
             raise ValueError("❌ VIOLATION CONTRAT (ResultatContexte): 'fichiers_readme' est une liste VIDE [] !")
        # historique peut être vide (nouveau chat)

@dataclass
class ResultatJuge:
    """
    SORTIE DE : AgentJuge
    Ce qu'il rend après avoir évalué la réponse.
    """
    valide: bool
    score: float
    raison: str
    details: Dict[str, Any]

    def __post_init__(self):
        if not isinstance(self.valide, bool):
            raise TypeError(f"❌ ResultatJuge: valide doit être un bool, reçu {type(self.valide)}")
        if not 0.0 <= self.score <= 5.0:
            raise ValueError(f"❌ ResultatJuge: score doit être entre 0 et 5, reçu {self.score}")
        if not self.raison:
            raise ValueError("❌ ResultatJuge: raison vide - données obligatoires manquantes!")

@dataclass
class Interaction:
    """
    L'Objet final sauvegardé sur le disque (JSON).
    """
    # --- 1. LE CONTENU (Signal) ---
    prompt: str                     # anc. user
    reponse: str                    # anc. assistant
    system: Optional[str]     # ✅ RAJOUTÉ (anc. system)

    # --- 2. LE CONTEXTE SÉMANTIQUE ---
    intention: ResultatIntention
    contexte_memoire : List[Souvenir]
    # --- 3. LA FICHE TECHNIQUE (Bruit) ---
    meta: MetadataFichier

@dataclass
class ContexteCode:
    """
    ATOME CODE : Format standard pour injection de contexte code.
    Flexible pour Classes, Méthodes et Fonctions.
    """
    # --- Identification (Obligatoire) ---
    id: str
    type: str
    module: str
    name: str

    # --- Contenu & Documentation (Avec défauts) ---
    signature: str = ""
    docstring: str = ""
    code_summary: str = ""
    contenu: str = ""  # ✅ Le corps du code (Optionnel car parfois on a juste la signature)

    # --- Analyse Structurelle (Listes vides par défaut) ---
    dependencies: List[Dict[str, Any]] = field(default_factory=list)
    key_concepts: List[str] = field(default_factory=list)
    variables_used: List[str] = field(default_factory=list)

    # --- Spécifique CLASSE (Optionnel) ---
    bases: List[str] = field(default_factory=list)
    attributes: Dict[str, str] = field(default_factory=dict)
    methods: List[str] = field(default_factory=list)

    # --- Spécifique FONCTION (Optionnel) ---
    return_type: Optional[str] = None

    # --- Méta ---
    score: float = 0.0

@dataclass
class AnalyseContenu:
    """Structure détaillée de l'analyse d'un code (AST)"""
    mode: str
    # ✅ On ajoute default_factory=list pour rendre le champ optionnel à l'instanciation
    fonctions: List[Dict[str, Any]] = field(default_factory=list)
    classes: List[Dict[str, Any]] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    # ✅ On autorise None par défaut
    docstring: Optional[str] = None
    erreurs: Optional[str] = None
    # ✅ On ajoute un dict vide par défaut
    extras: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ArtefactCode:
    """
    ATOME : Objet de transit pour un snippet ou fichier analysé.
    C'est le produit fini que le LLM a généré
    """
    id: str
    hash: str
    langage: str
    contenu: str
    timestamp: str
    analyse: AnalyseContenu  # ✅ Voici le champ officiel (remplace 'metadata')
    type: str

@dataclass
class CodeChunk:
    """
    Représente un fragment de code source technique.
    C'est la matière première a donner au LLM pour qu'il comprenne le projet.
    Distinct d'un 'Souvenir' qui est narratif/textuel.
    """
    contenu: str
    chemin: str      # ex: "agentique/base/META_agent.py"
    type: str        # ex: "fichier_complet", "fonction", "classe", "snippet"
    langage: str

@dataclass
class ResultatCode:
    """
    Représente l'état physique du code projet au moment T.
    Contient la structure et les fragments pertinents trouvés.
    Ne contient PAS de documentation externe (traitée à part).
    """
    squelette: str                         # L'arborescence du projet (Tree)
    chunks_vecteurs: List[ContexteCode]    # Les fragments de code similaires (RAG)

# ========================================
# 5. FORMATS PROMPTS (agent_Parole) STANDARDISÉS
# ========================================
# Mixin pour ajouter la méthode helper à tous les prompts
class PromptMixin:
    def get_unused_fields(self) -> List[str]:
        """Retourne les champs vides (None, liste vide, str vide)."""
        empty = []
        for f in fields(self):
            val = getattr(self, f.name)
            if val is None:
                empty.append(f.name)
            elif isinstance(val, (list, dict, set, str)) and len(val) == 0:
                empty.append(f.name)
        return empty

@dataclass
class StandardPrompt(PromptMixin):
    """
    Recette 1 : Chat Standard.
    Structure aplatie pour un accès direct aux composants du prompt.
    """
    prompt_original: str                                        # Le prompt utilisateur original
    instructions_systeme: str
    modificateurs: ModificateursCognitifs                       # Les modificateurs cognitifs
    intention: ResultatIntention                                # L'intention détectée
    historique: List[str]                                       # La conversation
    # CANAUX SÉPARÉS
    contexte_memoire: List[Souvenir]      # Mémoire (Vectoriel/Whoosh) -> Vient de AgentRecherche
    regles: List[Regle]          # Gouvernance -> Vient de AgentContexte
    fichiers_readme: List[FichierReadme]   # (README) -> Vient de AgentRecherche/Everything

    def __post_init__(self):
        # 1. Vérification des Chaines (Non vide)
        if not self.prompt_original or not self.prompt_original.strip():
            raise ValueError("❌ StandardPrompt: 'prompt_original' est vide ou ne contient que des espaces!")
        if not self.instructions_systeme:
            raise ValueError("❌ StandardPrompt: 'instructions_systeme' manquant!")
        # 2. Vérification des Listes (Doit contenir de la vraie donnée)
        # On vérifie que la liste n'est pas vide ET que son premier élément a du contenu
        if not self.contexte_memoire:
            raise ValueError("❌ StandardPrompt: Liste 'contexte_memoire' vide !")
        # Vérification profonde optionnelle (si tu veux être très strict)
        # if not any(s.contenu.strip() for s in self.souvenirs):
        #    raise ValueError("❌ StandardPrompt: Les souvenirs fournis sont tous vides (texte blanc)!")
        if not self.regles:
            raise ValueError("❌ StandardPrompt: Liste 'regles' vide (Gouvernance absente)!")
        if not self.fichiers_readme:
             raise ValueError("❌ StandardPrompt: Liste 'fichiers_readme' vide!")
        # 3. Vérification des Objets
        if self.modificateurs is None:
             raise ValueError("❌ StandardPrompt: 'modificateurs' est None")
        if self.intention is None:
             raise ValueError("❌ StandardPrompt: 'intention' est None")

@dataclass
class StandardPromptCode(PromptMixin):
    """
    Prompt dédié à l'ingénierie logicielle.
    Déclenché dès que de la matière 'Code' est trouvée.
    """
    prompt_original: str
    instructions_code_prompt: str
    modificateurs: ModificateursCognitifs
    intention: ResultatIntention
    historique: List[str]
    regles: List[Regle]           # Les règles s'appliquent aussi au code
    fichiers_readme: List[FichierReadme]    # La doc est pertinente pour le code
    code_chunks: List[CodeChunk]

    def __post_init__(self):
        if not self.prompt_original:
            raise ValueError("❌ StandardPromptCode: prompt_original vide - données obligatoires manquantes!")
        if not self.instructions_code_prompt:
            raise ValueError("❌ StandardPromptCode: instructions_code_prompt vide - données obligatoires manquantes!")
        if not self.code_chunks:
            raise ValueError("❌ StandardPromptCode: code_chunks vide - données obligatoires manquantes!")
        if not self.regles:
            raise ValueError("❌ StandardPromptCode: regles vide - données obligatoires manquantes!")
        if not self.fichiers_readme:
            raise ValueError("❌ StandardPromptCode: fichiers_readme vide - données obligatoires manquantes!")


@dataclass
class NewChatPrompt(PromptMixin):
    """
    Premier message d'un nouveau chat.
    Utilisé lorsque Semi détecte un salut ou qu'une commande système
    déclenche un redémarrage cognitif du dialogue.

    Ce prompt remplace le contexte normal : il injecte uniquement :
    - les règles actives
    - l'historique récent condensé
    - le résumé système global
    """
    prompt_original: str
    instructions_premier_prompt: str  # Texte brut d’instructions spécifiques
    modificateurs: ModificateursCognitifs
    intention: ResultatIntention
    dernier_historique_chat: List[str]      # Derniers messages utilisateur/assistant
    resume_systeme: str               # Résumé système (etat_systeme_resume.md)

@dataclass
class ManualContextCodePrompt(PromptMixin):
    """
    Prompt dédié au mode 'Contexte Manuel'.
    Remplace StandardPrompt quand des slots sont utilisés.
    """
    prompt_original: str
    instructions_contexte_manuel: str
    contexte_manuel: str
    intention: ResultatIntention                  # ResultatIntention
    historique: List[str]
    regles: List[Regle]               # List[Regle]
    fichiers_readme: List[FichierReadme]        # List[FichierReadme]
    modificateurs: ModificateursCognitifs              # ModificateursCognitifs

    def __post_init__(self):
        if not self.prompt_original:
            raise ValueError("❌ ManualContextCodePrompt: prompt_original vide - données obligatoires manquantes!")
        if not self.instructions_contexte_manuel:
            raise ValueError("❌ ManualContextCodePrompt: instructions_contexte_manuel vide - données obligatoires manquantes!")
        if not self.contexte_manuel:
            raise ValueError("❌ ManualContextCodePrompt: contexte_manuel vide - données obligatoires manquantes!")
        if not self.regles:
            raise ValueError("❌ ManualContextCodePrompt: regles vide - données obligatoires manquantes!")
        if not self.fichiers_readme:
            raise ValueError("❌ ManualContextCodePrompt: fichiers_readme vide - données obligatoires manquantes!")
# ========================================

@dataclass
class MemorySearchFirstPrompt:
    prompt_original: str
    instructions_first_search: str
    resultats_memoire: List[Souvenir]
    intention: ResultatIntention

    def __post_init__(self):
        if not self.prompt_original:
            raise ValueError("❌ MemorySearchFirstPrompt: prompt_original vide")
        if not self.instructions_first_search:
            raise ValueError("❌ MemorySearchFirstPrompt: instructions_first_search vide")
        if not self.resultats_memoire:
            raise ValueError("❌ MemorySearchFirstPrompt: resultats_memoire vide (La recherche a échoué ou est vide)")
@dataclass
class MemorySearchPrompt(PromptMixin):
    """
    Recette 3 : Recherche Mémoire (Boucle Réflexive).
    Utilisé lorsque le système renvoie à Semi les résultats de sa 'liste d'épicerie'.
    Correspond à l'étape 'Lecture des fichiers' du diagramme manuscrit.
    """
    prompt_original: str                # La demande initiale de Maxime
    instructions_memory_search_prompt: str  # Les consignes d'analyse (YAML)
    resultats_memoire: List[Souvenir]   # Les "Scripts entiers"
    raisonnement_precedent: str         # Ce que Semi a dit juste avant d'appeler l'outil (ex: "Je dois vérifier X...")
    intention: ResultatIntention

    def __post_init__(self):
        if not self.prompt_original:
            raise ValueError("❌ MemorySearchPrompt: prompt_original vide")
        if not self.instructions_memory_search_prompt:
            raise ValueError("❌ MemorySearchPrompt: instructions_memory_search_prompt vide")
        if not self.resultats_memoire:
            raise ValueError("❌ MemorySearchPrompt: resultats_memoire vide (La recherche a échoué ou est vide)")
@dataclass
class EtapePlan:
    """Une étape atomique du plan d'action de l'agent."""
    index: int
    description: str
    statut: str = "EN_ATTENTE" # EN_ATTENTE, EN_COURS, TERMINE, ECHOUE, ANNULE
    resultat: Optional[str] = None

@dataclass
class PlanExecution:
    """
    L'état stratégique de l'agent.
    Permet de persister la réflexion entre deux 'ticks' de la boucle de pensée.
    Agit comme une 'Mémoire de Travail Persistante' structurée.
    """
    objectif_global: str
    etapes: List[EtapePlan] = field(default_factory=list)
    index_etape_courante: int = 0
    est_termine: bool = False

    def obtenir_prochaine_etape(self) -> Optional[EtapePlan]:
        """Retourne l'étape active ou None si le plan est fini/invalide."""
        if 0 <= self.index_etape_courante < len(self.etapes):
            return self.etapes[self.index_etape_courante]
        return None

@dataclass
class CartographyPrompt(PromptMixin):
    """
    ÉTAPE 1 : VISION STRATÉGIQUE.
    Semi reçoit la 'project_map.json'.
    OBJECTIF UNIQUE : Identifier le prochain fichier critique à auditer.
    INTERDICTION : Ne pas analyser de code ici, juste des noms de fichiers.
    """
    prompt_original: str
    instructions_cartographie: str      # ex: "Tu es un Chef de Projet..."
    cartographie_projet: str            # Le contenu texte de project_map.json
    plan_de_bataille: List[str]         # Liste des fichiers déjà traités vs à faire
    intention: ResultatIntention

    def __post_init__(self):
        if not self.cartographie_projet:
            raise ValueError("❌ CartographyPrompt: cartographie vide!")

@dataclass
class FileInspectionPrompt(PromptMixin):
    """
    ÉTAPE 2 : ANALYSE TACTIQUE.
    Semi reçoit le contenu complet d'un seul fichier.
    OBJECTIF UNIQUE : Analyser le code, trouver des bugs ou proposer un refactoring.
    ACTION ATTENDUE : Appeler `update_system_summary` pour noter le fix, ou `final_answer` si fini.
    """
    prompt_original: str
    instructions_inspection: str        # ex: "Tu es un Expert Senior Python..."
    fichier_en_cours: Souvenir          # Le fichier ouvert sur l'établi
    notes_precedentes: str              # Contexte venant du plan (si applicable)
    intention: ResultatIntention

    def __post_init__(self):
        if not self.fichier_en_cours or not self.fichier_en_cours.contenu:
            raise ValueError("❌ FileInspectionPrompt: Aucun fichier sur l'établi !")

@dataclass
class StagingReviewPrompt(PromptMixin):
    """
    ÉTAPE 3 : CONSOLIDATION.
    Semi vient d'effectuer une modification (update_system_summary).
    OBJECTIF UNIQUE : Vérifier l'état du 'Staging' et décider de la prochaine étape.
    CHOIX : Revenir à la Cartographie (fichier suivant) ou terminer.
    """
    prompt_original: str
    instructions_review: str
    etat_staging_actuel: str            # Le contenu actuel de etat_systeme_resume.md
    derniere_action: str                # "J'ai ajouté le fix pour X"
    intention: ResultatIntention

# ========================================

@dataclass
class WebSearchPrompt(PromptMixin):
    """
    Recette 2 : Recherche Web Forcée.
    Contient uniquement la query et les résultats bruts.
    """
    query: str
    instructions_web_search_prompt: str
    resultats_web: List[Dict[str, str]] # [{'title':..., 'snippet':...}]
    # On garde un champ prompt_original pour cohérence si besoin, ou on l'utilise comme query

    def __post_init__(self):
        if not self.query:
            raise ValueError("❌ WebSearchPrompt: query vide - données obligatoires manquantes!")
        if not self.resultats_web:
            raise ValueError("❌ WebSearchPrompt: resultats_web vide - données obligatoires manquantes!")

@dataclass
class ProtocolePrompt(PromptMixin):
    """
    Recette 4 : Protocole d'Intervention ALERTE (!!!).
    Remplace le System Prompt standard par le protocole de sécurité.
    """
    prompt_original: str
    protocole_contenu: str          # Le contenu du fichier .md
    historique_recent: List[str]    # Les 10 derniers messages
    intention: ResultatIntention    # L'intention (souvent forcée à GOUVERNANCE)
    regles: List[Regle]          # Les règles actives (souvent vides ici, car le protocole prime)

    def __post_init__(self):
        if not self.prompt_original:
            raise ValueError("❌ ProtocolePrompt: prompt_original vide - données obligatoires manquantes!")
        if not self.protocole_contenu:
            raise ValueError("❌ ProtocolePrompt: protocole_contenu vide - données obligatoires manquantes!")

# ========================================
# 6. GOUVERNANCE & RÉFLEXIVITÉ
# ========================================

class TypeEcart(EnumFlexible):
    """Catégorisation des erreurs réflexives."""
    HALLUCINATION = "Hallucination"       # Invention de faits ou fichiers
    GOUVERNANCE = "Gouvernance"           # Non-respect d'une instruction explicite
    LOGIQUE = "Logique"                   # Erreur de raisonnement ou contradiction
    BIAIS = "Biais"                       # Pattern hérité de l'entraînement (ex: dossier Documentation/)
    VISUEL = "Visuel"                     # Contradiction entre image et texte
    TECHNIQUE = "Technique"               # Erreur d'exécution de code ou path

@dataclass
class EntreeJournalReflexif:
    """
    ATOME RÉFLEXIF : Structure stricte pour journal_de_doute_reflexif.md.
    Basé sur le format 'Perfect Example' du 2025-06-25.
    """
    erreur_commise: str                   # Fait brut (ex: "Proposition hors racine")
    type_ecart: TypeEcart                 # Catégorie abstraite
    contexte: str                         # Quand et sur quel sujet
    regle_enfreinte: str                  # Citation de la "Loi" (Fichier + Section)
    hypothese_causale: str                # Métacognition : Pourquoi j'ai failli ?
    correction_injectee: str              # Action corrective immédiate

    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M"))

    def to_markdown(self) -> str:
        """Génère le bloc Markdown formaté pour le journal."""
        # Récupération propre de la valeur de l'Enum
        ecart_str = self.type_ecart.value if isinstance(self.type_ecart, Enum) else str(self.type_ecart)

        return (
            f"\n🔁 Entrée réflexive — {self.timestamp}\n"
            f"- **Erreur commise** : {self.erreur_commise}\n"
            f"- **Type d’écart** : {ecart_str}\n"
            f"- **Contexte** : {self.contexte}\n"
            f"- **Règle enfreinte** : {self.regle_enfreinte}\n"
            f"- **Hypothèse causale** : {self.hypothese_causale}\n"
            f"- **Correction injectée** : {self.correction_injectee}\n"
        )

# ========================================
#  --- STATS_MANAGER --- GESTION STANDARDISÉE DES STATISTIQUES
# ========================================

@dataclass
class StatsBase:
    nom_agent: str
    appels_total: int = 0
    erreurs_total: int = 0
    derniere_execution: Optional[str] = None
    timestamp_creation: str = field(default_factory=lambda: datetime.now().isoformat())
    stats_specifiques: Dict[str, Any] = field(default_factory=dict)
    temps_moyen_ms: Optional[float] = None

    def incrementer_appel(self) -> None:
        self.appels_total += 1
        self.derniere_execution = datetime.now().isoformat()

    def incrementer_erreur(self) -> None:
        self.erreurs_total += 1

    def ajouter_stat_specifique(self, nom: str, valeur_initiale: Any = 0) -> None:
        if nom not in self.stats_specifiques:
            self.stats_specifiques[nom] = valeur_initiale

    def incrementer_stat_specifique(self, nom: str, increment: int = 1) -> None:
        if nom in self.stats_specifiques:
            if isinstance(self.stats_specifiques[nom], (int, float)):
                self.stats_specifiques[nom] += increment
        else:
            self.stats_specifiques[nom] = increment

    def definir_stat_specifique(self, nom: str, valeur: Any) -> None:
        """Définit ou remplace la valeur d'une statistique spécifique."""
        self.stats_specifiques[nom] = valeur

    def obtenir_stat_specifique(self, nom: str, defaut: Any = None) -> Any:
        """Récupère la valeur d'une statistique spécifique."""
        return self.stats_specifiques.get(nom, defaut)

    def existe_stat_specifique(self, nom: str) -> bool:
        """Vérifie si une statistique spécifique existe."""
        return nom in self.stats_specifiques

    def obtenir_statistiques(self) -> Dict[str, Any]:
        taux_reussite = 0.0
        if self.appels_total > 0:
            taux_reussite = ((self.appels_total - self.erreurs_total) / self.appels_total) * 100

        return {
            "agent": self.nom_agent,
            "appels_total": self.appels_total,
            "erreurs_total": self.erreurs_total,
            "taux_reussite": round(taux_reussite, 2),
            "derniere_activite": self.derniere_execution,
            "timestamp_creation": self.timestamp_creation,
            "stats_specifiques": self.stats_specifiques.copy()
        }

    def obtenir_resume(self) -> str:
        stats = self.obtenir_statistiques()
        return (
            f"Agent: {stats['agent']} | "
            f"Appels: {stats['appels_total']} | "
            f"Erreurs: {stats['erreurs_total']} | "
            f"Taux réussite: {stats['taux_reussite']}%"
        )

    def reinitialiser(self) -> None:
        self.appels_total = 0
        self.erreurs_total = 0
        self.derniere_execution = None
        self.stats_specifiques.clear()

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "appels_total": self.appels_total,
            "erreurs_total": self.erreurs_total,
            "derniere_execution": self.derniere_execution,
            **self.stats_specifiques
        }

# ========================================
# FIN DU FICHIER
# ========================================

@dataclass
class DataFormat:
    """
    CONTRAT D'INGESTION : Standard pour le futur dataset d'entraînement.
    Inspiré par l'approche Data-Centric de SecondMind.
    """
    # --- CONTENU ---
    text: str                       # Le corps du texte (Markdown recommandé)
    titre: str                      # Identifiant source (ex: "Pydantic_V2_Docs")

    # --- TAXONOMIE ---
    sujet: str                      # Science, Musique, Maths, Biologie...
    categorie: str                  # Manuel, Papier_Recherche, Snippet_Technique

    # --- MÉTADONNÉES DE QUALITÉ ---
    source_url: Optional[str] = None
    date_scraping: str = field(default_factory=lambda: datetime.now().isoformat())
    nb_tokens: int = 0              # Estimé par ton futur pipeline
    score_qualite_initial: float = 1.0  # 0.0 à 1.0 (basé sur le filtrage sémantique)
    force_logique: float = 1.0      # Degré de certitude de l'information (ex: 1.0 pour une preuve mathématique, 0.5 pour une théorie sociale).
    potentiel_lien_transversal: List[str] = field(default_factory=list)  # Liste des concepts universels identifiés (ex: ["entropie", "feedback_loop", "symétrie"]).
    alerte_biais: Dict[str, Any] = field(default_factory=dict)  # Identification des biais potentiels présents dans la source pour que le modèle apprenne à les reconnaître.

    # --- MÉTRAGES POUR L'ENTRAÎNEMENT ---
    langue: str = "fr"
    metadata_complexite: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        # Validation stricte pour garantir un dataset propre
        if not self.text or len(self.text) < 100:
            raise ValueError("❌ DataFormat: Texte trop court ou vide pour l'entraînement.")
        if not self.sujet:
            raise ValueError("❌ DataFormat: Le sujet est obligatoire pour la segmentation.")

@dataclass
class CriteresEvaluationSecondMind:
    """
    GRILLE DE VÉRITÉ : Évalue la pertinence d'un texte selon les 10 piliers.
    Chaque score est compris entre 0.0 et 1.0.
    """
    # --- PHASE 1 : DÉBUG ET VALIDATION ---
    indice_debug_biais: float = 0.0      # Pilier 1 : Présence de patterns de défaillance connus
    score_fractalite: float = 0.0        # Pilier 2 : Le concept s'applique-t-il à plusieurs échelles ?
    poids_causalite: float = 0.0         # Pilier 3 : Preuve de lien causal vs corrélation

    # --- PHASE 2 : FONDATION ET ÉMERGENCE ---
    densite_axiome: float = 0.0          # Pilier 4 : Proximité avec les lois irréductibles
    potentiel_emergence: float = 0.0     # Pilier 5 : Capacité du concept à créer de la complexité

    # --- PHASE 3 : LIMITES ET RÉEL ---
    score_incompletude: float = 0.0      # Pilier 6 : Reconnaissance explicite des limites du modèle
    validation_empirique: float = 0.0    # Pilier 7 : Lien avec des données réelles/expérimentales

    # --- PHASE 4 : SYNTHÈSE ET INTUITION ---
    force_convergence: float = 0.0       # Pilier 8 : Nombre de domaines confirmant cette vérité
    capacite_compression: float = 0.0    # Pilier 9 : Potentiel de "saut logique" (intuition fondée)
    transposabilite: float = 0.0         # Pilier 10 : Facilité à être extrait et réutilisé ailleurs

    def score_global(self) -> float:
        """Calcule la note finale de 'Vérité Profonde'."""
        # On peut pondérer certains piliers (ex: Axiomes et Causalité pèsent plus lourd)
        champs = fields(self)
        return sum(getattr(self, f.name) for f in champs) / len(champs)
