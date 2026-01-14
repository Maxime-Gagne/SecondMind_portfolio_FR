#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
META AGENT - Métaclasse pour injection automatique des outils communs
"""
import functools
import time
from typing import Any, Callable, Dict, List, Optional
from agentique.base.auditor_base import AuditorBase
from agentique.base.contrats_interface import StatsBase
from agentique.base.cognitive_logger import CognitiveLogger


class MemoireTravailRAM:
    """Memoire RAM - Version complète avec toutes les méthodes"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.memoire_ram = []
            cls._instance.stats = {
                "items_travail_ajoutes": 0,
                "items_evalues": 0,
                "items_valides": 0,
                "items_rejetes": 0,
                "items_remplaces": 0
            }
        return cls._instance

    def ajouter_travail(self, item: dict) -> bool:
        if not isinstance(item, dict) or "contenu" not in item:
            return False
        self.memoire_ram.append(item)
        return True

    def recuperer_travail(self) -> list[dict]:
        return self.memoire_ram.copy()

    def remplacer_travail(self, nouveaux_items: list[dict]) -> bool:
        if not isinstance(nouveaux_items, list):
            return False
        self.memoire_ram = nouveaux_items.copy()
        return True

    def evaluer_travail(self, items_valides: list[dict]) -> bool:
        """COPIÉ TEL QUEL depuis AgentMemoire"""
        # Vider la mémoire de travail actuelle
        self.vider_travail()

        # Réinjecter les items valides
        for item in items_valides:
            self.ajouter_travail(item)  # Passer l'item TEL QUEL
        return True

    def obtenir_stats_travail(self) -> dict:
        """Retourne les statistiques de la mémoire RAM."""
        try:
            # On retourne simplement les statistiques internes
            return self.stats_manager.obtenir_statistiques()
        except Exception as e:
            return {"erreur": str(e)}

    def vider_travail(self) -> int:
        compteur = len(self.memoire_ram)
        self.memoire_ram = []
        return compteur

class MetaAgent(type):
    """Métaclasse qui injecte les outils ET le monitoring automatique."""

    def __call__(cls, *args, **kwargs):
        # 1. CRÉATION (Coquille vide)
        # On n'utilise PAS super().__call__ car cela lancerait __init__ trop tôt.
        # On crée juste l'instance vierge.
        instance = cls.__new__(cls)

        # 2. IDENTIFICATION
        nom_agent_display = cls.__name__.replace("Agent", "")
        nom_agent_audit = nom_agent_display.lower()


        # 3. INJECTION DES DÉPENDANCES (Avant le __init__ pour être dispo)
        # (Imports locaux pour éviter les cycles, ou déplace-les en haut du fichier)
        from agentique.base.contrats_interface import StatsBase
        from agentique.base.auditor_base import AuditorBase
        from agentique.base.cognitive_logger import CognitiveLogger

        # Injection RAM (Assure-toi que la classe est dispo ou importée)
        # instance.memoire_ram = MemoireTravailRAM() # Si définie dans le même fichier ou importée

        instance.stats_manager = StatsBase(nom_agent_display)
        instance.auditor = AuditorBase(nom_agent_audit)

        instance.logger = CognitiveLogger(
            nom_agent=nom_agent_display,
            auditor=instance.auditor,
            console_output=True
        )

        # 4. INJECTION DES UTILITAIRES (Correction : Assignation explicite)
        # On attache ces méthodes à l'instance pour qu'elles soient utilisables via self.calculer_pertinence(...)
        instance.calculer_pertinence = lambda p, e: MetaAgent._calculer_pertinence_commun(instance, p, e)
        instance.valider_echange = lambda d, dest: MetaAgent._valider_echange_commun(instance, d, dest)

        # 5. 🔥 AUTO-INSTRUMENTATION (Câblage des stats)
        # On parcourt le dictionnaire de la classe pour trouver ses propres méthodes
        for attr_name, attr_value in cls.__dict__.items():

            # On ne cible que les fonctions publiques
            if callable(attr_value) and not attr_name.startswith("_"):

                # On utilise ta méthode statique existante pour créer le wrapper
                # (Assure-toi que _creer_wrapper_stats est bien définie dans MetaAgent ou AgentBase)
                if hasattr(MetaAgent, '_creer_wrapper_stats'):
                    decorated_method = MetaAgent._creer_wrapper_stats(
                        instance,
                        attr_value,
                        attr_name
                    )

                    # On remplace la méthode sur l'instance (Override)
                    setattr(instance, attr_name, decorated_method)

        # 6. INITIALISATION STANDARD (Lancement réel)
        # Maintenant que tout est prêt (Logger, Stats, Wrappers), on peut laisser l'agent démarrer
        cls.__init__(instance, *args, **kwargs)

        print(f"✅ {cls.__name__} initialisé et instrumenté.")
        return instance
    # --------------------------------------------------------------------------
    # STATS_MANAGER -- WRAPPER DE MÉTHODES
    # --------------------------------------------------------------------------
    @staticmethod
    def _creer_wrapper_stats(instance, method, method_name):
        """Crée un wrapper qui loggue les appels et les erreurs automatiquement."""
        @functools.wraps(method)
        def wrapper(*method_args, **method_kwargs):
            # 1. Incrémenter l'appel global
            instance.stats_manager.incrementer_appel()

            # 2. Incrémenter la stat spécifique de la méthode
            nom_stat_methode = f"appels_{method_name}"
            instance.stats_manager.incrementer_stat_specifique(nom_stat_methode)

            # Utilisation de perf_counter pour une mesure précise
            start_time = time.perf_counter()
            succes = False

            try:
                # Exécution réelle de la méthode
                result = method(instance, *method_args, **method_kwargs)
                succes = True
                return result

            except Exception as e:
                # En cas d'erreur
                instance.stats_manager.incrementer_erreur()
                instance.stats_manager.incrementer_stat_specifique(f"erreurs_{method_name}")
                raise e
            finally:
                # 3. Calcul temps exécution et CONNEXION DE LA VARIABLE
                duration_ms = (time.perf_counter() - start_time) * 1000

                # Si l'auditor le supporte, on enregistre cette métrique précieuse
                if hasattr(instance.auditor, 'enregistrer_stat'):
                    try:
                        instance.auditor.enregistrer_stat(
                            method_name,
                            {
                                "succes": succes,
                                "duree_ms": duration_ms
                            }
                        )
                    except Exception:
                        pass # On évite de crasher le wrapper si l'auditor n'est pas prêt

        return wrapper

    @staticmethod
    def _calculer_pertinence_commun(agent_instance, prompt: str, element: Any) -> float:
        prompt_mots = set(prompt.lower().split())
        element_mots = set(str(element).lower().split())
        if not prompt_mots or not element_mots: return 0.0
        intersection = prompt_mots.intersection(element_mots)
        union = prompt_mots.union(element_mots)
        score = len(intersection) / len(union) if union else 0.0
        agent_instance.logger.log_thought(f"Score pertinence calculé: {score:.2f}")
        return score

    @staticmethod
    def _valider_echange_commun(agent_instance, data: Any, agent_destination: str) -> bool:
        valide = agent_instance.auditor.valider_echange(data, agent_destination)
        if valide:
            agent_instance.logger.info(f"✅ Échange validé vers {agent_destination}")
        else:
            agent_instance.logger.log_warning(f"❌ Échange invalide vers {agent_destination}")
        return valide

# CLASSE DE BASE OPTIONNELLE
# ========================================

class AgentBase(metaclass=MetaAgent):
    """
    Classe de base optionnelle pour les agents
    Hériter de cette classe applique automatiquement MetaAgent
    """
    auditor: 'AuditorBase'
    # Ces déclarations sont CRUCIALES pour Pylint
    stats_manager: 'StatsBase'
    memoire_ram: 'MemoireTravailRAM'
    logger: 'CognitiveLogger'
    def __init__(self, nom_agent: str = None):
        """
        Initialisation de base
        Le nom sera extrait automatiquement si non fourni
        """

        if nom_agent:
            self.nom = nom_agent
        else:
            self.nom = self.__class__.__name__.replace("Agent", "")
        # Le reste de l'initialisation (auditor, stats_manager, logger, etc.)
        # est géré par la métaclasse MetaAgent avant l'appel à __init__.

__all__ = ['MetaAgent', 'AgentBase']
