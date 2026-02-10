#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RechercheWeb - Module de Deep Research.
Implémente une boucle cognitive : Search -> Scrape -> Evaluate -> Repeat.
Utilise BeautifulSoup pour la lecture profonde et le LLM pour l'évaluation de pertinence.
"""

import time
import requests
import json
import re
from typing import List, Dict, Tuple
from bs4 import BeautifulSoup
# --- IMPORT SÉCURISÉ ---
try:
    from duckduckgo_search import DDGS
    DDGS_AVAILABLE = True
except ImportError:
    DDGS = None
    DDGS_AVAILABLE = False

from agentique.base.META_agent import AgentBase

class RechercheWeb(AgentBase):
    def __init__(self, moteur_llm):
        super().__init__(nom_agent="RechercheWeb")
        
        if not moteur_llm:
            raise RuntimeError("RechercheWeb nécessite un MoteurLLM pour évaluer le contenu.")
        
        self.moteur_llm = moteur_llm
        
        # Configuration Haute Capacité (RTX 3090 / Qwen 128k)
        self.MAX_CONTENT_LEN = 100000  # ~25k tokens, très large pour ne pas limiter
        self.MAX_TOURS = 4             # Nombre max d'itérations de recherche
        self.SEUIL_SUFFISANCE = 8      # Sur 10, pour arrêter la recherche
        self.TIMEOUT_REQUEST = 10      # Secondes pour le scraping

    # =========================================================================
    # 1. PLANIFICATION (Query Expansion)
    # =========================================================================

    def _generer_requetes(self, objectif: str, connaissances_actuelles: str = "") -> List[str]:
        """Génère des requêtes de recherche optimisées selon ce qu'on sait déjà."""
        
        prompt = f"""Tu es un expert en recherche d'information (OSINT).
Objectif : "{objectif}"
Ce que nous savons déjà : "{connaissances_actuelles[:500]}..."

Génère 3 requêtes de recherche Google/DuckDuckGo précises pour trouver l'information manquante ou approfondir le sujet.
Format de réponse attendu : Une liste JSON stricte de chaînes de caractères.
Exemple : ["python snake game logic", "pygame tutorial", "snake game algorithm"]

TES REQUÊTES (JSON) :"""

        try:
            # On utilise generer (non-stream) car on veut un JSON court
            reponse = self.moteur_llm.generer(prompt)
            texte = reponse.get("response", "").strip()
            
            # Nettoyage Markdown éventuel
            texte = texte.replace("```json", "").replace("```", "").strip()
            
            requetes = json.loads(texte)
            if isinstance(requetes, list):
                return requetes[:3] # On garde le top 3
            return [objectif]
            
        except Exception as e:
            self.logger.log_warning(f"Erreur génération requêtes: {e}, fallback sur l'objectif.")
            return [objectif]

    # =========================================================================
    # 2. EXPLORATION (Search & Scrape)
    # =========================================================================
    
    def _rechercher_urls(self, query: str) -> List[Dict]:
        """Récupère les URLs via DuckDuckGo."""
        if not DDGS_AVAILABLE:
            self.logger.log_error("Impossible de chercher : Module duckduckgo_search manquant.")
            return []

        self.logger.info(f"🔍 Recherche : '{query}'")
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=4))
                return results
        except Exception as e:
            self.logger.log_error(f"Erreur DDGS: {e}")
            return []

    def _scraper_url(self, url: str) -> str:
        """Télécharge et nettoie le contenu d'une page Web."""
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            response = requests.get(url, headers=headers, timeout=self.TIMEOUT_REQUEST)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Suppression du bruit (scripts, styles, pubs)
            for script in soup(["script", "style", "nav", "footer", "header", "aside"]):
                script.extract()
            
            # Extraction texte
            text = soup.get_text(separator='\n')
            
            # Nettoyage des lignes vides multiples
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = '\n'.join(chunk for chunk in chunks if chunk)
            
            # Troncature Haute Limite
            if len(text) > self.MAX_CONTENT_LEN:
                self.logger.info(f"✂️ Contenu tronqué à {self.MAX_CONTENT_LEN} chars (Original: {len(text)})")
                return text[:self.MAX_CONTENT_LEN]
            
            return text
            
        except Exception as e:
            self.logger.log_warning(f"Échec scraping {url}: {e}")
            return ""

    # =========================================================================
    # 3. ÉVALUATION (Le Juge Interne)
    # =========================================================================

    def _analyser_contenu(self, contenu: str, url: str, objectif: str) -> Dict:
        """
        Demande au LLM d'évaluer la pertinence et d'extraire les infos.
        Retourne un dict {score, extraction, suffisance}.
        """
        prompt = f"""[ANALYSEUR DE RECHERCHE]
Objectif utilisateur : "{objectif}"

Voici le contenu extrait de {url} :
---DÉBUT---
{contenu[:15000]} ... (tronqué pour analyse)
---FIN---

TA MISSION :
1. Évalue la Pertinence (/10) : Est-ce utile pour l'objectif ?
2. Évalue la Suffisance (/10) : À quel point cela répond-il à TOUT l'objectif ?
3. Extrait les informations clés (Synthèse).

Réponds STRICTEMENT au format JSON :
{{
    "pertinence": int,
    "suffisance": int,
    "extraction": "Résumé détaillé des points clés trouvés..."
}}
"""
        try:
            res = self.moteur_llm.generer(prompt)
            texte_json = res.get("response", "").strip()
            # Nettoyage markdown
            texte_json = re.sub(r'```json\s*|\s*```', '', texte_json)
            
            data = json.loads(texte_json)
            return data
        except Exception as e:
            self.logger.log_error(f"Erreur analyse LLM: {e}")
            return {"pertinence": 0, "suffisance": 0, "extraction": ""}

    # =========================================================================
    # 4. BOUCLE PRINCIPALE (Orchestration)
    # =========================================================================

    def executer_recherche_profonde(self, objectif: str) -> str:
        """
        Lance la boucle de recherche itérative.
        Retourne une synthèse complète.
        """
        connaissances_accumulees = ""
        urls_visitees = set()
        score_suffisance_global = 0
        tour = 0
        
        self.logger.info(f"🚀 Démarrage Deep Research sur : '{objectif}'")

        while tour < self.MAX_TOURS and score_suffisance_global < self.SEUIL_SUFFISANCE:
            tour += 1
            self.logger.info(f"🔄 Tour {tour}/{self.MAX_TOURS} (Suffisance actuelle: {score_suffisance_global}/10)")
            
            # A. Planification
            requetes = self._generer_requetes(objectif, connaissances_accumulees)
            
            for query in requetes:
                # B. Recherche
                resultats = self._rechercher_urls(query)
                
                for res in resultats:
                    url = res['href']
                    if url in urls_visitees: continue
                    urls_visitees.add(url)
                    
                    # C. Lecture (Scraping)
                    self.logger.info(f"📖 Lecture : {res['title']}")
                    contenu_brut = self._scraper_url(url)
                    
                    if len(contenu_brut) < 500: # Trop court, on passe
                        continue
                        
                    # D. Évaluation
                    analyse = self._analyser_contenu(contenu_brut, url, objectif)
                    
                    pertinence = analyse.get('pertinence', 0)
                    suffisance_page = analyse.get('suffisance', 0)
                    
                    if pertinence >= 6: # Seuil de qualité
                        connaissances_accumulees += f"\n\nSOURCE: {res['title']} ({url})\n"
                        connaissances_accumulees += f"INFO: {analyse.get('extraction')}\n"
                        
                        # Mise à jour du score global (On prend le max de ce qu'on a trouvé)
                        score_suffisance_global = max(score_suffisance_global, suffisance_page)
                        self.logger.info(f"✅ Info pertinente trouvée (Score: {pertinence}, Suffisance: {suffisance_page})")
                    else:
                        self.logger.info(f"🗑️ Rejeté (Pertinence faible: {pertinence})")
                        
                    if score_suffisance_global >= self.SEUIL_SUFFISANCE:
                        self.logger.info("🎯 Suffisance atteinte ! Arrêt prématuré.")
                        break
                
                if score_suffisance_global >= self.SEUIL_SUFFISANCE: break
            
            # Petite pause pour être poli avec les serveurs
            time.sleep(1)

        # Synthèse Finale
        rapport_final = (
            f"### RÉSULTAT DE RECHERCHE PROFONDE\n"
            f"**Objectif :** {objectif}\n"
            f"**Sources consultées :** {len(urls_visitees)}\n"
            f"**Score de complétude :** {score_suffisance_global}/10\n\n"
            f"--- SYNTHÈSE DES DONNÉES ---\n"
            f"{connaissances_accumulees}"
        )
        
        return rapport_final