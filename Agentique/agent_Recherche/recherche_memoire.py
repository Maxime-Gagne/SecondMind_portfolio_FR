#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RechercheMemoireTool - Interface d'Exécution et de Formatage I/O
Module "Tool" servant de pont entre l'intelligence de l'agent (Semi/Master) et
la puissance brute de l'AgentRecherche.

Rôle Architectural :
    Ce module agit comme une couche d'abstraction (Facade Pattern). Il traduit les
    intentions de haut niveau de l'agent (ex: "Je veux voir le code de X") en
    commandes techniques précises pour le moteur sous-jacent.

Responsabilités :
    1. **Routing** : Dispatche les requêtes vers le bon moteur (Vectoriel, Everything, Whoosh).
    2. **Normalisation** : Nettoie les entrées (regex sur noms de fichiers) et standardise les sorties.
    3. **Lecture Physique** : Récupère le contenu "Vérité Terrain" des fichiers sur le disque.
    4. **Cartographie** : Fournit à l'agent la vision structurelle du projet (Project Map).
"""

import re
import time
import json
from pathlib import Path
from typing import List, Dict, Any

from agentique.base.contrats_interface import Souvenir
from agentique.base.config_paths import ROOT_DIR


class RechercheMemoireTool:
    """
    Outil opérationnel de manipulation de la mémoire et du système de fichiers.

    Cette classe encapsule la logique de récupération de données pour la rendre
    digeste par un LLM. Elle transforme des chemins de fichiers et des vecteurs
    en objets 'Souvenir' formatés (Markdown), prêts à être injectés dans le contexte.

    Attributes:
        agent_recherche (AgentRecherche): Instance du moteur I/O injectée par dépendance.
    """

    def __init__(self, agent_recherche):
        self.agent_recherche = agent_recherche

    # =========================================================================
    # 🧠 MÉTHODES DE TRAITEMENT (Appelées par Semi)
    # =========================================================================

    def executer(self, type_recherche: str, query: str) -> Dict[str, Any]:
        """
        Dispatcheur central des requêtes de recherche (Pattern Strategy).

        Traduit un `type_recherche` abstrait en appel de méthode concret sur AgentRecherche.
        Permet au LLM d'utiliser un vocabulaire simple ("code", "concept") sans connaître
        la complexité sous-jacente (Everything vs Faiss vs Whoosh).

        Args:
            type_recherche (str): L'intention de recherche ("verbatim", "code", "concept", "readme").
            query (str): La requête utilisateur ou le terme à chercher.

        Returns:
            Dict[str, Any]: Résultat standardisé contenant succès, contenus et métadonnées.
        """
        resultat = None

        try:
            # 1. Recherche de Code / Fichiers Projet
            if type_recherche == "code" or type_recherche == "fichier":
                # Mappe vers : recherche_fichier_hors_memoire (Everything + GitIgnore)
                resultat = self.agent_recherche.recherche_fichier_hors_memoire(query)

            # 2. Recherche de Citation Exacte
            elif type_recherche == "verbatim" or type_recherche == "citation":
                # Mappe vers : recuperer_resume_par_session (Whoosh + Check Disque)
                resultat = self.agent_recherche.recuperer_resume_par_session(query)

            # 3. Recherche de Concept / Souvenir flou
            elif type_recherche == "concept" or type_recherche == "souvenir":
                # Mappe vers : recherche_contexte_memoire_vectorielle (Sans intention ici, c'est une requête brute)
                resultat = self.agent_recherche.recherche_contexte_memoire_vectorielle(
                    query
                )

            # 4. Recherche Documentation Globale
            elif type_recherche == "readme" or type_recherche == "doc":
                # Mappe vers : rechercher_readme
                docs = self.agent_recherche.rechercher_readme(query)
                # On convertit manuellement en ResultatRecherche pour uniformiser la sortie outil
                return {
                    "type": "documentation",
                    "count": len(docs),
                    "items": [d.contenu[:500] + "..." for d in docs],  # Preview
                }

            else:
                return {"error": f"Type de recherche inconnu : {type_recherche}"}

            # Formatage de la réponse pour le LLM
            if resultat:
                return {
                    "succes": True,
                    "nb_resultats": resultat.nb_fichiers_scannes,
                    "contenus": [s.contenu for s in resultat.souvenirs_bruts],
                    "sources": [s.titre for s in resultat.souvenirs_bruts],
                }
            else:
                return {"succes": False, "message": "Aucun résultat trouvé."}

        except Exception as e:
            return {"error": f"Erreur outil recherche: {str(e)}"}

    def traiter_recherche_memoire(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Traite une demande de récupération de fichiers multiples (Batch Processing).

        Capable d'analyser une requête complexe (ex: "agent_A.py et config.yaml"),
        de découper les cibles via Regex, et de retourner une liste d'objets Souvenir atomiques.
        C'est la méthode principale pour "charger" du code en mémoire de travail.

        Args:
            arguments (Dict): Payload contenant 'queries' (liste) ou 'query' (str).

        Returns:
            Dict: Payload de type 'MEMORY_RESULTS' contenant la liste des objets Souvenir.
        """
        # 1. Normalisation en liste
        raw_queries = arguments.get("queries", [arguments.get("query", "")])
        if isinstance(raw_queries, str):
            raw_queries = [raw_queries]

        # 2. Découpage intelligent (Virgules, 'et', 'and') pour obtenir des fichiers atomiques
        final_queries = []
        for q in raw_queries:
            # Regex : cherche une suite de lettres/chiffres/underscores/tirets
            # se terminant par .py, .md, .yaml, .json, etc.
            pattern = r"[\w\-\.]+\.(?:py|md|yaml|yml|json|txt)"
            fichiers_detectes = re.findall(pattern, q, flags=re.IGNORECASE)

            if fichiers_detectes:
                final_queries.extend(fichiers_detectes)
            else:
                # Fallback si aucun suffixe n'est trouvé (recherche classique)
                final_queries.append(q.strip())

        # 3. Exécution itérative -> Création d'une liste de Souvenirs
        payload_souvenirs = []

        for target in final_queries:
            # Nettoyage (au cas où le LLM envoie "fichier.py | intention")
            nom_fichier = target.split("|")[0].strip()

            # Lecture via la méthode interne
            contenu_fichier = self.lire_fichier_complet(nom_fichier)

            # Création de l'objet Souvenir atomique
            payload_souvenirs.append(
                Souvenir(
                    titre=nom_fichier,
                    contenu=contenu_fichier,
                    type="fichier_technique",
                    score=1.0,
                )
            )

        return {
            "type": "MEMORY_RESULTS",
            "payload": payload_souvenirs,
            "original_query": final_queries,
        }

    def traiter_lecture_fichier(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Alias direct pour lire un fichier unique."""
        filename = arguments.get("filename", "") or arguments.get("queries", [""])[0]
        content = self.lire_fichier_complet(filename)
        return {
            "type": "MEMORY_RESULTS",
            "payload": [
                Souvenir(
                    titre=filename, contenu=content, type="fichier_brut", score=1.0
                )
            ],
            "original_query": filename,
        }

    def traiter_lecture_cartographie(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Charge la "Carte du Monde" du projet (Conscience Situationnelle).

        Lit le fichier `project_map.json` généré par l'AgentAuditor pour donner à l'agent
        une vue d'ensemble de l'arborescence des fichiers. Essentiel pour éviter les
        hallucinations sur des noms de fichiers ou des chemins inexistants.

        Returns:
            Dict: Le contenu structuré de l'arborescence du projet.
        """
        map_path = ROOT_DIR / "mapping_structure" / "project_map.json"

        if not map_path.exists():
            return {
                "type": "MEMORY_RESULTS",
                "payload": [
                    Souvenir(
                        titre="Erreur_Cartographie",
                        contenu="Le fichier project_map.json n'existe pas. Lance un audit (AgentAuditor) pour le générer.",
                        type="erreur_systeme",
                        score=0.0,
                    )
                ],
                "original_query": "cartographie",
            }

        try:
            with open(map_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # On transforme le JSON en liste lisible pour le LLM
            # data est sous la forme { "path/to/file.py": "Description", ... }
            liste_fichiers = sorted(data.keys())
            formatted_list = "\n".join([f"- {f}" for f in liste_fichiers])

            contenu_reponse = (
                f"🗺️ **CARTOGRAPHIE DU PROJET** (Source: AgentAuditor)\n"
                f"Total fichiers indexés: {len(liste_fichiers)}\n\n"
                f"{formatted_list}\n\n"
                f"👉 _Copie ces chemins dans ton plan d'action pour itérer dessus._"
            )

            return {
                "type": "MEMORY_RESULTS",
                "payload": [
                    Souvenir(
                        titre="project_map.json",
                        contenu=contenu_reponse,
                        type="cartographie_projet",
                        score=1.0,
                    )
                ],
                "original_query": "lire_cartographie",
            }

        except Exception as e:
            return {
                "type": "MEMORY_RESULTS",
                "payload": [
                    Souvenir(
                        titre="Erreur_Lecture_Map",
                        contenu=f"Erreur lecture JSON: {e}",
                        type="erreur_systeme",
                        score=0.0,
                    )
                ],
                "original_query": "cartographie",
            }

    # =========================================================================
    # 🔧 MÉTHODES INTERNES (Lecture Physique)
    # =========================================================================

    def lire_fichier_complet(self, nom_fichier: str) -> str:
        """
        Lecture physique et formatage contextuel d'un fichier (Ground Truth).

        Utilise `AgentRecherche` pour localiser le fichier sur le disque (résolution de chemin),
        puis lit son contenu brut et l'encapsule dans des balises Markdown (Syntax Highlighting)
        pour une ingestion optimale par le LLM.

        Gère les cas d'erreur (Fichier introuvable) pour fournir un feedback utile à l'agent
        plutôt que de crasher.

        Args:
            nom_fichier (str): Nom ou chemin partiel du fichier.

        Returns:
            str: Contenu formaté ou message d'erreur explicite.
        """
        # 1. Localisation via AgentRecherche (Everything)
        chemins = self.agent_recherche.localiser_fichiers_physiques(nom_fichier)

        # CAS A : FICHIER NON TROUVÉ
        if not chemins:
            return (
                f"❌ [FICHIER INTROUVABLE] : '{nom_fichier}'\n"
                f"   (Le fichier n'existe pas ou le nom est incorrect dans le projet)"
            )

        # CAS B : FICHIER TROUVÉ
        target_path = Path(chemins[0])

        try:
            if not target_path.is_file():
                return (
                    f"⚠️ [ERREUR] '{target_path.name}' est un dossier, pas un fichier."
                )

            # Lecture brute
            contenu = target_path.read_text(encoding="utf-8", errors="replace")

            # Détection extension pour syntax highlighting
            ext = target_path.suffix.lower().replace(".", "")
            if not ext:
                ext = "text"

            # SORTIE NEUTRE (Juste la data)
            return (
                f"📄 **FICHIER**: `{target_path.name}`\n"
                f"📍 Path: `{target_path}`\n"
                f"```{ext}\n"
                f"{contenu}\n"
                f"```\n"
                f"--- Fin du fichier {target_path.name} ---"
            )
        except Exception as e:
            return f"❌ [ERREUR LECTURE] {target_path.name}: {e}"
