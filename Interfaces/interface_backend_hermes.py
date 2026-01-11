#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Backend SecondMind - Version finale (Portfolio Ready).
Simplifié avec config_paths.py.
"""

# ==============================================================================
# SECTION 0 : CONFIGURATION ET IMPORTS ROBUSTES
# ==============================================================================

import sys
import os
import json
import yaml
import shutil
import logging
import threading
import time
import webbrowser
import subprocess
import uuid
from pathlib import Path
from datetime import datetime

# --- FIX CRITIQUE WINDOWS (Doit être fait AVANT tout import de colorama/flask) ---
if sys.platform == 'win32':
    os.environ["COLORAMA_DISABLE"] = "1"

# Imports Tiers
try:
    import colorama
    colorama.just_fix_windows_console = lambda *a, **k: None

    import click
    click.echo = lambda *a, **k: sys.stdout.write(a[0] if a else "")

    import pynvml
    from flask import Flask, request, jsonify, send_from_directory, Response, stream_with_context
    from flask_cors import CORS
    from flask_socketio import SocketIO, emit
    from ruamel.yaml import YAML
except ImportError as e:
    print(f"❌ Erreur critique d'import tiers : {e}")
    sys.exit(1)


# --- Initialisation du Logger (fait en premier pour être toujours disponible) ---
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] {%(levelname)s} - %(message)s')
logging.getLogger('werkzeug').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# --- AJOUT AUDIO ---
import tempfile
try:
    import whisper
    import torch
    # Chargement du modèle sur le GPU (RTX 3090)
    # "small" est très rapide, "medium" est plus précis. Avec ta 3090, tu peux mettre "medium" ou "large-v2" sans souci.
    device = "cpu"
    logger.info(f"🎧 Chargement de Whisper sur {device}...")
    audio_model = whisper.load_model("medium", device=device)
    WHISPER_AVAILABLE = True
    logger.info("✅ Whisper chargé et prêt à écouter.")
except ImportError:
    WHISPER_AVAILABLE = False
    logger.warning("⚠️ Whisper non installé (pip install openai-whisper). L'audio ne fonctionnera pas.")
except Exception as e:
    WHISPER_AVAILABLE = False
    logger.error(f"⚠️ Erreur chargement Whisper: {e}")
# ==============================================================================
# 🎯 BOOTSTRAP : CHARGEMENT CENTRALISÉ DES CHEMINS
# ==============================================================================
try:
    # 1. On repère où on est pour trouver la racine
    # interface_backend_hermes.py est dans : root/Nuclear_Formation_Datacenter/connect_backend_Semi/
    current_file = Path(__file__).resolve()
    # On remonte jusqu'à la racine supposée (D:/rag_personnel)
    project_root_guess = current_file.parent.parent.parent

    # 2. Injection de la racine dans le PATH pour permettre les imports absolus
    if str(project_root_guess) not in sys.path:
        sys.path.insert(0, str(project_root_guess))

    # 3. Import de la Source de Vérité (config_paths)
    from agentique.base.config_paths import (
        ROOT_DIR,
        AGENTIQUE_DIR,
        MEMOIRE_DIR,
        DATA_TRAINING_CENTER_DIR
    )

    # 4. Définition des chemins spécifiques au Backend (non présents dans config_paths)
    NUCLEAR_FORMATION_DIR = ROOT_DIR / "Nuclear_Formation_Datacenter"

    logger.info(f"✅ Chemins chargés via config_paths. Racine: {ROOT_DIR}")

except ImportError as e:
    logger.critical(f"❌ Impossible d'importer agentique.base.config_paths : {e}")
    logger.critical("Vérifiez que 'agentique' est bien un package (avec __init__.py) et accessible.")
    sys.exit(1)
except Exception as e:
    logger.critical(f"❌ Erreur lors de l'initialisation des chemins : {e}")
    sys.exit(1)

# ==============================================================================
# SECTION 1 : IMPORTS DU PROJET & INITIALISATION
# ==============================================================================

try:
    from agentique.Semi.agent_Semi import AgentSemi
    from agentique.base.gardien_projet import GardienProjet
    from agentique.base.auditor_base import AuditorBase
    from routes_modules_externes import router_externes, init_external_routes
    from agentique.base.contrats_interface import CustomJSONEncoder
    from agentique.sous_agents_gouvernes.agent_Auditor.agent_Auditor import AgentAuditor
    SEMI_DISPONIBLE = True
except Exception as e:
    logger.critical(f"❌ ERREUR IMPORTS AGENTS: {e}", exc_info=True)
    SEMI_DISPONIBLE = False
    sys.exit(1)

# ==============================================================================
# FLASK & AGENT
# ==============================================================================

app = Flask(__name__, static_folder='memoire', static_url_path='/static')
app.json_encoder = CustomJSONEncoder
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")
app.register_blueprint(router_externes)

# --- Monitoring GPU ---
NVML_DISPONIBLE = False
gpu_handle = None
try:
    pynvml.nvmlInit()
    gpu_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
    NVML_DISPONIBLE = True
    logger.info("✅ NVML initialisé pour monitoring GPU")
except Exception as e:
    logger.warning(f"⚠️ NVML non disponible: {e}")

def get_vram_usage():
    if NVML_DISPONIBLE and gpu_handle:
        try:
            return pynvml.nvmlDeviceGetMemoryInfo(gpu_handle).used / (1024**3)
        except: return 0.0
    return 0.0

# --- Initialisation Agent Semi ---
try:
    # Cache global pour Prompt Viewer
    prompt_viewer_cache = {
        "raw_prompt": "En attente...",
        "timestamp": datetime.now().isoformat()
    }
    prompt_viewer_lock = threading.Lock()

    def get_last_prompt_cache(): return prompt_viewer_cache
    def get_prompt_lock(): return prompt_viewer_lock

    agent_semi = AgentSemi(
        get_cache=get_last_prompt_cache,
        get_lock=get_prompt_lock,
        socketio=socketio
    )
    logger.info("✅ Pipeline AgentSemi initialisé (SocketIO injecté).")

    # Audit au démarrage
    try:
        auditor_sys = AgentAuditor()

        # 🆕 CORRECTION ENCODAGE AUTO (Avant l'audit complet)
        logger.info("🔍 [Gardien] Vérification des encodages...")
        stats_enc = auditor_sys.corriger_tous_encodages()
        if stats_enc['fichiers_corriges'] > 0:
            logger.info(f"🔧 Encodage réparé pour {stats_enc['fichiers_corriges']} fichiers.")

        # Audit normal
        rapport = auditor_sys.auditer_systeme()
        logger.info(f"🔍 Audit système complété – {rapport['nb_fichiers']} fichiers.")
    except Exception as e:
        logger.error(f"❌ Audit système échoué: {e}")

    intention_detector = agent_semi.intention_detector
    init_external_routes(agent_semi)

except Exception as e:
    logger.critical(f"❌ ERREUR CRITIQUE AgentSemi: {e}", exc_info=True)
    raise

# ==============================================================================
# ROUTE POUR L'AUDITOR COMPLET AU DÉMARRAGE
# ==============================================================================
@app.route('/api/audit/systeme', methods=['POST'])
def api_audit_systeme():
    try:
        auditor = AgentAuditor()
        rapport = auditor.auditer_systeme()
        return rapport, 200
    except Exception as e:
        return {"erreur": str(e)}, 500

@app.route('/api/audit/encodage', methods=['POST'])
def audit_encodage():
    try:
        auditor = AgentAuditor()
        rapport = auditor.auditer_encodage_fichiers()
        return jsonify(rapport)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/audit/corriger_encodage', methods=['POST'])
def corriger_encodage():
    try:
        auditor = AgentAuditor()
        stats = auditor.corriger_tous_encodages()
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
# ==============================================================================
# SECTION GARDIEN : SYNCHRONISATION DES STATS
# (Logique de synchronisation_stats.py, intégrée au backend)
# ==============================================================================

class SynchroniseurStats:
    """
    Gestionnaire de stats autonome (Rotation, Backup, Sync).
    Gère les doublons de fichiers config et le mapping des noms.
    """

    def __init__(self, agent_instance: AgentSemi):
        self.agent_semi = agent_instance
        self.backup_dir = ROOT_DIR / "agentique" / "base" / "monitoring" / "config_backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.erreurs = []
        self.succes = []
        # Set pour éviter de traiter 2 fois le même fichier (ex: MoteurLLM et IntentionDetector partagent la config)
        self.fichiers_traites_ce_tour = set()

        self.yaml = YAML()
        self.yaml.preserve_quotes = True
        self.yaml.default_flow_style = False
        self.yaml.width = 4096
        self.yaml.indent(mapping=2, sequence=2, offset=0)

    def convertir_nom_agent_pour_auditor(self, nom_agent: str) -> str:
        """
        Mappe le nom de l'instance vers le nom EXACT du fichier config.
        Ex: "AgentMemoire" -> "memoire" (pour trouver config_memoire.yaml)
        """
        # Mapping strict : Nom de Classe -> Suffixe du fichier config
        mapping = {
            "AgentSemi": "semi",
            "AgentMemoire": "memoire",
            "AgentRecherche": "recherche",
            "AgentRechercheCode": "recherchecode",
            "AgentContexte": "contexte",
            "AgentParole": "parole",
            "AgentJuge": "juge",
            "AgentReflexor": "reflexor",
            "AgentAuditor": "auditor",
            "MoteurLLM": "moteurllm", # Vérifie si c'est config_moteurllm.yaml ou config_llm.yaml chez toi
            "MoteurMiniLLM": "moteurminillm",
            "IntentionDetector": "intentiondetector",
        }

        if nom_agent in mapping:
            return mapping[nom_agent]

        # Fallback de nettoyage agressif si l'agent n'est pas dans la liste
        nom_clean = nom_agent.lower().replace("agent", "").replace("moteur", "").replace("_", "")
        return nom_clean

    def creer_backup(self, config_path: Path) -> bool:
        """Crée un backup horodaté ET nettoie les anciens (Rotation)."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            nom_backup = f"{config_path.stem}_backup_{timestamp}.yaml"
            backup_path = self.backup_dir / nom_backup

            # Backup (Copie sécurisée reconnue par Auditor)
            shutil.copy2(config_path, backup_path)

            # Rotation (Garde les 3 derniers)
            pattern = f"{config_path.stem}_backup_*.yaml"
            tous_les_backups = sorted(
                self.backup_dir.glob(pattern),
                key=lambda x: x.stat().st_mtime,
                reverse=True
            )

            for f in tous_les_backups[3:]:
                try:
                    f.unlink() # Suppression tolérée car précédée d'une copie
                except Exception: pass

            return True
        except Exception as e:
            logger.warning(f"⚠️ Erreur backup stats: {e}")
            return False

    def mettre_a_jour_dashboard(self, config_data: dict, stats_agent: dict) -> dict:
        appels = stats_agent.get("appels_total", 0)
        erreurs = stats_agent.get("erreurs_total", 0)
        succes = (1 - (erreurs / max(1, appels))) * 100

        config_data['dashboard_stats'] = {
            "derniere_mise_a_jour": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "appels_total": appels,
            "erreurs_total": erreurs,
            "taux_de_succes": f"{succes:.2f}%",
            "specifiques": stats_agent.get("stats_specifiques", {})
        }
        return config_data

    def synchroniser_agent(self, nom_agent: str, stats_agent: dict) -> bool:
        """Traite un agent spécifique."""
        try:
            nom_auditor = self.convertir_nom_agent_pour_auditor(nom_agent)

            # Récupération du chemin via une instance temporaire d'Auditor
            auditor_temp = AuditorBase(nom_auditor)
            path_str = auditor_temp.get_path("config")

            if not path_str:
                # Ce n'est pas une erreur critique, certains agents n'ont pas de config
                return False

            path_obj = Path(path_str).resolve()

            # 🛑 ANTI-DOUBLON : Si ce fichier a déjà été traité ce tour-ci, on skip
            if path_obj in self.fichiers_traites_ce_tour:
                return True

            # On marque le fichier comme traité
            self.fichiers_traites_ce_tour.add(path_obj)

            if not path_obj.exists():
                return False

            # Exécution de la sauvegarde
            if self.creer_backup(path_obj):
                with open(path_obj, 'r', encoding='utf-8') as f:
                    data = self.yaml.load(f)

                if data:
                    data = self.mettre_a_jour_dashboard(data, stats_agent)

                    # Sauvegarde atomique
                    tmp = path_obj.with_suffix('.tmp')
                    with open(tmp, 'w', encoding='utf-8') as f:
                        self.yaml.dump(data, f)
                    shutil.move(str(tmp), str(path_obj))

                    logger.info(f"     ✅ Stats synchronisées pour {nom_agent}")
                    self.succes.append(nom_agent)
                    return True

            return False

        except Exception as e:
            self.erreurs.append((nom_agent, str(e)))
            return False

    def executer(self) -> dict:
        self.erreurs = []
        self.succes = []
        self.fichiers_traites_ce_tour = set() # Reset du cache anti-doublon

        try:
            etat_cognitif = self.agent_semi.obtenir_etat_cognitif()

            for nom_agent, stats in etat_cognitif.items():
                self.synchroniser_agent(nom_agent, stats)

        except Exception as e:
            return {"status": "error", "message": str(e)}

        return {"status": "success", "updated": len(self.succes)}

@app.route('/api/stats/sync', methods=['POST'])
def route_synchroniser_stats():
    """Appelé par le Gardien pour synchroniser les stats."""
    try:
        sync = SynchroniseurStats(agent_semi)
        res = sync.executer()
        return jsonify(res), 200 if res["status"] == "success" else 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ==============================================================================
# SECTION 2 : ROUTES FLASK
# ==============================================================================
@app.route('/transcribe', methods=['POST'])
def transcribe():
    """Reçoit un blob audio, le sauvegarde temporairement et le transcrit."""
    if not WHISPER_AVAILABLE:
        return jsonify({"text": "[Erreur: Whisper n'est pas installé ou chargé sur le serveur]"}), 500

    if 'audio' not in request.files:
        return jsonify({"error": "Aucun fichier audio reçu"}), 400

    try:
        audio_file = request.files['audio']

        # Création d'un fichier temporaire pour que ffmpeg puisse le lire
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
            temp_path = temp_wav.name
            audio_file.save(temp_path)

        # Transcription
        # fp16=False aide parfois à la compatibilité si les drivers cuda font des siennes,
        # mais avec ta 3090 True devrait marcher. On laisse True par défaut.
        result = audio_model.transcribe(temp_path, fp16=True, language='fr')
        transcription = result['text'].strip()

        logger.info(f"🎤 Audio transcrit: {transcription}")

        # Nettoyage
        try:
            os.remove(temp_path)
        except: pass

        return jsonify({"text": transcription})

    except Exception as e:
        logger.error(f"❌ Erreur transcription: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/formation_data/<path:filename>')
def serve_formation_data(filename):
    """
    Sert les fichiers depuis le dossier NUCLEAR_FORMATION_DIR.
    """
    return send_from_directory(str(NUCLEAR_FORMATION_DIR), filename)

@app.route("/")
def index():
    """Sert la page hub_de_secondmind.html comme page d'accueil."""
    return send_from_directory(str(NUCLEAR_FORMATION_DIR), "hub_de_secondmind.html")


@app.route('/command', methods=['POST'])
def handle_command():
    try:
        data = request.json
        user_prompt = data.get('prompt')
        search_mode = data.get('search_mode', 'auto')
        manual_context = data.get('manual_context', None)
        if manual_context and len(manual_context.strip()) > 0:
            logger.info("⚡ Détection de Slots actifs : Passage forcé en mode 'manual_context'")
            search_mode = 'manual_context'
        enable_thinking = data.get('enable_thinking', False)

        # ID venant de l'interface (Peut être None si "Nouvelle discussion" pas encore créée)
        conversation_id = data.get('conversation_id', None)

        if not user_prompt:
            return jsonify({"error": "Prompt requis"}), 400

        # =================================================================
        # LOGIQUE DE DISSOCIATION (Groupe UI vs Interaction Agent)
        # =================================================================

        # 1. ID pour l'Agent (Mémoire Interne : Brute/Historique)
        # Si pas d'ID UI, on génère un ID "Fantôme" (UUID) unique pour cette interaction.
        # L'agent pourra ainsi sauvegarder son travail sans faire planter le système.
        import uuid
        agent_session_id = conversation_id if conversation_id else str(uuid.uuid4())

        archive_history = []

        # 2. Gestion de l'Historique UI (Conversation Manager)
        # ⚠️ VERROU STRICT : ON NE TOUCHE AU MANAGER QUE SI ID EXPLICITE
        if conversation_id:
            # C'est une conversation nommée/existante : on la met à jour dans le dossier 'conversations'
            conversation_manager.add_message(conversation_id, 'user', user_prompt)

            # On récupère l'historique pour le donner à l'IA en contexte
            full_history = conversation_manager.get_archive_history(conversation_id)
            if full_history:
                # On retire le dernier message (le prompt actuel) pour éviter la duplication
                archive_history = full_history[:-1]

        # SINON (Si conversation_id est None/Vide) :
        # On ne fait RIEN avec conversation_manager.
        # Résultat : Pas de fichier créé dans 'conversations/', pas de pollution visuelle.
        # Mais l'agent reçoit quand même un 'agent_session_id' valide pour ses dossiers internes (brute/historique).

        logger.info(f"Streaming pour: {user_prompt[:80]}... (ID Agent: {agent_session_id})")

        socketio.emit('generation_start', {
            'prompt': user_prompt[:100],
            'vram_gb': get_vram_usage()
        })

        def generate():
            full_response = ""
            try:
                # 3. Génération via l'Agent
                # IMPORTANT : On passe 'agent_session_id' pour que l'agent sache où écrire sa mémoire brute
                for token in agent_semi.penser(
                    user_prompt,
                    stream=True,
                    search_mode=search_mode,
                    historique_brut=manual_context,
                    enable_thinking=enable_thinking,
                    archive_history=archive_history,
                    session_id=agent_session_id  # <--- ID Agent (Brute/Hist)
                ):
                    full_response += token
                    yield token.encode('utf-8')

                # 4. Fin de génération : Sauvegarde Session UI (Assistant)
                # ⚠️ VERROU STRICT : On ne sauvegarde dans le manager que si c'était une vraie conversation UI
                if conversation_id:
                    conversation_manager.add_message(conversation_id, 'assistant', full_response)

            except Exception as e:
                logger.error(f"Erreur stream: {e}")
                yield f"[Erreur: {str(e)}]".encode('utf-8')
            finally:
                socketio.emit('generation_end', {'message': 'Generation complete'})

        return Response(stream_with_context(generate()), mimetype='text/plain', direct_passthrough=True)

    except Exception as e:
        logger.error(f"Erreur /command: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route('/memoire', methods=['POST', 'HEAD', 'OPTIONS'])
def handle_memoire():
    """Route pour gestion de la mémoire et injection de contenu"""

    # Gestion CORS
    if request.method == 'OPTIONS':
        return '', 200

    # Check de connexion (utilisé par l'interface)
    if request.method == 'HEAD':
        return '', 200

    # Injection de mémoire
    if request.method == 'POST':
        try:
            data = request.json

            # Injection de mémoire générale
            if 'memoire' in data:
                contenu_memoire = data['memoire']
                logger.info(f"Injection mémoire: {contenu_memoire[:100]}...")

                success = agent_semi.agent_memoire.sauvegarder_memoire(
                    contenu=contenu_memoire,
                    type_memoire="persistante",
                    nom_fichier=f"injection_interface_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                )

                if success:
                    return jsonify({"status": "success", "message": "Mémoire injectée avec succès"})
                else:
                    return jsonify({"error": "Échec de l'injection mémoire"}), 500

            # Injection de feedback avec classification automatique
            elif 'feedback' in data:
                contenu_feedback = data['feedback']
                # AJOUTEZ CE LOG POUR DÉBOGUER
                logger.info(f"DEBUG: Tentative de validation +1. État de dernier_code_hash : {getattr(agent_semi, 'dernier_code_hash', 'non défini')}")

                # Validation de code avec +1
                if contenu_feedback.strip() == "+1":
                    if hasattr(agent_semi, 'dernier_code_hash') and agent_semi.dernier_code_hash:
                        success = agent_semi.version_tracker.marquer_valide(
                            agent_semi.dernier_code_hash,
                            "Validé via +1"
                        )
                        if success:
                            return jsonify({
                                "status": "success",
                                "message": "✅ Code validé !",
                                "code_validated": True
                            })
                        else:
                            return jsonify({"error": "Code introuvable"}), 404
                # Note négative avec -1 (pour futur usage)
                elif contenu_feedback.strip() == "-1":
                    # Pour l'instant, juste feedback normal
                    pass

                # Sinon, traitement normal du feedback
                classification = agent_semi.intention_detector.intention_detector(contenu_feedback)

                # 🟢 CORRECTION : Définition du chemin dans le sous-dossier 'feedback'
                sous_dossier = "feedback"
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')

                # Nom de fichier : feedback/sujet_action_categorie_timestamp.json
                nom_fichier_avec_sous_dossier = (
                    f"{sous_dossier}/"
                    f"{classification.sujet.value.lower()}_"
                    f"{classification.action.value.lower()}_"
                    f"{classification.categorie.value.lower()}_"
                    f"feedback_{timestamp}.json" # Changement de .txt à .json
                )

                # 🟢 CORRECTION : Structuration du contenu pour le JSON
                contenu_structuré = {
                    "feedback": contenu_feedback,
                    "classification": {
                        "sujet": classification.sujet.value,
                        "action": classification.action.value,
                        "categorie": classification.categorie.value
                    },
                    "timestamp": datetime.now().isoformat()
                }

                logger.info(f"Classification feedback: {classification.sujet.name}/{classification.action.name}/{classification.categorie.name}")

                success = agent_semi.agent_memoire.sauvegarder_memoire(
                    contenu=contenu_structuré, # Utilisation du contenu structuré
                    type_memoire="reflexive",
                    nom_fichier=nom_fichier_avec_sous_dossier # Utilisation du chemin du sous-dossier
                )

                # NOTE: L'AgentMemoire.sauvegarder_memoire est censé gérer l'indexation.
                # Si elle ne le fait pas, l'appel à update_index doit être séparé et cibler le chemin.
                # Par simplicité, on le laisse de côté pour éviter une erreur d'indexation whoosh incomplète.

                if success:
                    return jsonify({
                        "status": "success",
                        "message": f"Feedback ajouté à reflexive/{sous_dossier}",
                        "filename": nom_fichier_avec_sous_dossier,
                        "classification": {
                            "sujet": classification.sujet.value,
                            "action": classification.action.value,
                            "categorie": classification.categorie.value
                        }
                    })
                else:
                    return jsonify({"error": "Échec de l'ajout de feedback"}), 500

            else:
                return jsonify({"error": "Type de contenu non reconnu"}), 400

        except Exception as e:
            logger.error(f"Erreur injection mémoire: {e}")
            return jsonify({"error": f"Erreur serveur: {str(e)}"}), 500

@app.route('/health', methods=['GET', 'HEAD', 'OPTIONS'])
def health_check():
    """Endpoint léger pour le monitoring de santé"""
    if request.method == 'OPTIONS':
        return '', 200
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()}), 200

# ==============================================================================
# UTILITAIRES BENCHMARK
# ==============================================================================

BENCHMARK_LOG_FILE = MEMOIRE_DIR / "benchmarks" / "benchmark_history.jsonl"
BENCHMARK_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

def _process_benchmark_config(profile_data: dict, default_ctx: int, default_gpu: int) -> dict:
    """
    Helper interne pour extraire les données d'un profil de modèle
    et les formater pour le frontend benchmark_dual_llm.html.
    """
    loading_config = profile_data.get('loading', {})

    config = {}
    # Extrait les clés attendues par le frontend
    config['n_ctx'] = loading_config.get('context_window', default_ctx)
    config['n_gpu_layers'] = loading_config.get('gpu_layers', default_gpu)
    config['model'] = profile_data.get('model_path', 'N/A') # Clé à la racine du profil

    # On peut ajouter le nom du modèle pour affichage
    config['model_name'] = profile_data.get('model_name', 'Inconnu')
    return config

@app.route('/api/config_benchmark', methods=['GET'])
def get_benchmark_config():
    """
    Fournit les configurations pour le DUAL LLM BENCHMARK LAB.
    Lit les profils actifs de 'moteurllm' et 'moteurminillm'
    et les formate pour le frontend.
    """
    benchmark_config = {}
    yaml_loader = YAML(typ='safe') # Utilise le loader de hermes.py

    try:
        main_llm_path = agent_semi.auditor.get_path("config", "moteurllm")

        if not main_llm_path or not Path(main_llm_path).exists():
            raise FileNotFoundError("Config 'moteurllm' introuvable via auditor.")

        with open(main_llm_path, 'r', encoding='utf-8') as f:
            data = yaml_loader.load(f)

        # 1. Lire le profil actif (ex: 'qwen_14b')
        active_profile_key = data['active_profile']
        # 2. Extraire les données de ce profil (ex: data['models']['qwen_14b'])
        profile_data = data['models'][active_profile_key]

        # 3. Formater pour le frontend
        benchmark_config['main_llm'] = _process_benchmark_config(profile_data, 8192, -1) # Default Qwen

        # --- Mini LLM (MoteurMiniLLM) ---
        mini_llm_path = agent_semi.auditor.get_path("config", "moteurminillm")
        if not mini_llm_path or not Path(mini_llm_path).exists():
            mini_llm_path = agent_semi.auditor.get_path("config", "minillm") # Fallback
            if not mini_llm_path or not Path(mini_llm_path).exists():
                raise FileNotFoundError("Config 'moteurminillm' ou 'minillm' introuvable.")

        with open(mini_llm_path, 'r', encoding='utf-8') as f:
            data = yaml_loader.load(f)

        # 1. Lire le profil actif (ex: 'Phi3Q4')
        active_profile_key = data['active_profile_mini_llm']
        # 2. Extraire les données de ce profil
        profile_data = data['models'][active_profile_key]

        # 3. Formater pour le frontend
        benchmark_config['mini_llm'] = _process_benchmark_config(profile_data, 4096, 35) # Default Phi3

        return jsonify(benchmark_config)

    except FileNotFoundError as e:
        logger.error(f"Erreur de configuration Benchmark : Fichier non trouvé - {e}")
        return jsonify({"error": f"Fichier de configuration manquant : {e}"}), 500
    except KeyError as e:
        logger.error(f"Erreur de configuration Benchmark : Clé manquante (profil introuvable?) - {e}")
        return jsonify({"error": f"Erreur de clé dans le YAML : {e}"}), 500
    except Exception as e:
        logger.error(f"Erreur lors du chargement de la configuration benchmark : {e}", exc_info=True)
        return jsonify({"error": "Erreur interne lors de la lecture de la configuration."}), 500

def log_benchmark_result(test_type, metrics, prompt):
    """Enregistre les résultats du benchmark dans un fichier journal"""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "test_type": test_type,
        "metrics": metrics,
        "prompt_preview": prompt[:50] + "..."
    }

    try:
        with open(BENCHMARK_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.error(f"Erreur log benchmark: {e}")

def get_precise_vram():
    """Récupère la VRAM utilisée instantanée"""
    if NVML_DISPONIBLE and gpu_handle:
        try:
            info = pynvml.nvmlDeviceGetMemoryInfo(gpu_handle)
            return info.used / (1024**3) # En GB
        except: return 0.0
    return 0.0

# ==============================================================================
# ROUTES OFFICIELLES : DUAL LLM BENCHMARK
# ==============================================================================

@app.route('/api/benchmark/main_llm', methods=['POST'])
def benchmark_main_llm():
    """Test de performance brute du Main LLM (Mistral/Qwen...)"""
    try:
        data = request.json
        prompt = data.get('prompt', "Explique la théorie de la relativité.")

        logger.info(f"🔬 BENCHMARK MAIN START: {prompt}")

        # Mesures
        start_time = time.time()
        tokens_count = 0
        first_token_time = None
        last_token_time = None
        inter_token_latencies = []

        # Utilisation du vrai moteur LLM
        # On force une génération streamée pour compter les tokens
        generator = agent_semi.moteur_llm.generer_stream(prompt)

        for _ in generator:
            current_token_time = time.time()

            # 1. Capture du TTFT
            if first_token_time is None:
                first_token_time = current_token_time

            # 2. Capture de la latence inter-token
            if last_token_time is not None:
                latency_ms = (current_token_time - last_token_time) * 1000
                inter_token_latencies.append(latency_ms)

            last_token_time = current_token_time
            tokens_count += 1

        end_time = time.time()

        # --- NOUVEAUX CALCULS ---
        total_time = end_time - start_time
        ttft_ms = (first_token_time - start_time) * 1000 if first_token_time else 0
        avg_inter_token_latency_ms = sum(inter_token_latencies) / len(inter_token_latencies) if inter_token_latencies else 0
        tokens_per_sec = tokens_count / total_time if total_time > 0 else 0
        vram = get_precise_vram()

        results = {
            "tokens_per_sec": round(tokens_per_sec, 2),
            "vram_gb": round(vram, 2),
            "ttft_ms": round(ttft_ms, 0),
            "avg_inter_token_latency_ms": round(avg_inter_token_latency_ms, 0),
            "total_time_s": round(total_time, 2),
            "tokens_count": tokens_count,

            # ✅ AJOUT : Alias pour le tableau historique du frontend
            "main_tokens_per_sec": round(tokens_per_sec, 2),
            "total_vram_gb": round(vram, 2)
        }
        # --- FIN NOUVEAUX CALCULS ---

        log_benchmark_result("MAIN_LLM", results, prompt)
        return jsonify(results)

    except Exception as e:
        logger.error(f"Erreur Benchmark Main: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/benchmark/mini_llm', methods=['POST'])
def benchmark_mini_llm():
    """Test de performance brute du Mini LLM (Phi-3...)"""
    try:
        data = request.json
        prompt = data.get('prompt', "Classification: Bonjour")

        logger.info(f"🔬 BENCHMARK MINI START: {prompt}")

        start_time = time.time()
        tokens_count = 0
        first_token_time = None
        last_token_time = None
        inter_token_latencies = []

        # On accède au moteur Mini LLM.
        # Note: Si votre architecture n'expose pas directement 'moteur_mini_llm' sur l'agent,
        # adaptez ce chemin (ex: agent_semi.intention_detector.llm_client...)
        moteur_cible = getattr(agent_semi, 'moteur_mini_llm', None)

        if not moteur_cible:
            # Fallback: on essaie de le trouver dans le détecteur d'intention
            if hasattr(agent_semi, 'intention_detector'):
                 moteur_cible = getattr(agent_semi.intention_detector, 'moteur_mini_llm', None)

        # --- GESTION STREAM / NON-STREAM ---
        if hasattr(moteur_cible, 'generer_stream'):
            generator = moteur_cible.generer_stream(prompt)
            for _ in generator:
                current_token_time = time.time()

                if first_token_time is None:
                    first_token_time = current_token_time

                if last_token_time is not None:
                    latency_ms = (current_token_time - last_token_time) * 1000
                    inter_token_latencies.append(latency_ms)

                last_token_time = current_token_time
                tokens_count += 1

            end_time = time.time()

        else:
            # Fallback si pas de stream (mesure le temps total comme TTFT)
            logger.warning("Moteur Mini LLM n'a pas 'generer_stream'. Benchmark de latence dégradé.")
            reponse_dict = moteur_cible.generer(prompt)
            reponse_texte = reponse_dict.get("response", "")

            end_time = time.time()
            first_token_time = end_time
            tokens_count = len(reponse_texte.split()) # Estimation très approximative

        # --- NOUVEAUX CALCULS ---
        total_time = end_time - start_time
        ttft_ms = (first_token_time - start_time) * 1000 if first_token_time else 0
        avg_inter_token_latency_ms = sum(inter_token_latencies) / len(inter_token_latencies) if inter_token_latencies else 0
        tokens_per_sec = tokens_count / total_time if total_time > 0 else 0
        vram = get_precise_vram()

        results = {
        "tokens_per_sec": round(tokens_per_sec, 2),
        "vram_gb": round(vram, 2),
        "ttft_ms": round(ttft_ms, 0),
        "avg_inter_token_latency_ms": round(avg_inter_token_latency_ms, 0),
        "total_time_s": round(total_time, 2),
        "tokens_count": int(tokens_count),
        # ✅ AJOUT : Alias pour le tableau historique du frontend
        "mini_tokens_per_sec": round(tokens_per_sec, 2),
        "total_vram_gb": round(vram, 2)
        }
        # --- FIN NOUVEAUX CALCULS ---

        log_benchmark_result("MINI_LLM", results, prompt)
        return jsonify(results)

    except Exception as e:
        logger.error(f"Erreur Benchmark Mini: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/benchmark/full_pipeline', methods=['POST'])
def benchmark_full_pipeline():
    """Test du flux complet avec calcul précis du T/s de génération"""
    try:
        data = request.json
        prompt = data.get('prompt', "Aide-moi à coder une fonction Python.")

        logger.info(f"🔬 BENCHMARK PIPELINE START: {prompt}")

        start_total = time.time()

        # 1. Mesure Classification
        start_classif = time.time()
        intention = agent_semi.intention_detector.intention_detector(prompt)
        end_classif = time.time()
        classif_time_ms = (end_classif - start_classif) * 1000

        # 2. Mesure Pipeline (RAG + Génération)
        start_process = time.time()

        # On force le stream pour compter les tokens
        generator = agent_semi.penser(prompt, stream=True)

        tokens_count = 0
        first_token_time = None

        for _ in generator:
            if first_token_time is None:
                first_token_time = time.time() # Le premier mot apparaît ici
            tokens_count += 1

        end_total = time.time()

        # --- CALCULS AVANCÉS ---

        # A. Latence RAG (Temps d'attente avant le premier mot, moins la classif)
        # C'est le temps que Semi a passé à "réfléchir/chercher"
        if first_token_time:
            rag_latency_s = first_token_time - start_process
            generation_time_s = end_total - first_token_time
        else:
            rag_latency_s = end_total - start_process
            generation_time_s = 0.001 # Évite division par zéro

        # B. Tokens par seconde (Sur la génération pure uniquement)
        tokens_per_sec = tokens_count / generation_time_s if generation_time_s > 0 else 0

        vram = get_precise_vram()

        results = {
            "classification_time_ms": round(classif_time_ms, 0),
            "rag_latency_s": round(rag_latency_s, 2),
            "generation_time_s": round(generation_time_s, 2),
            "total_time_s": round(end_total - start_total, 2),
            "tokens_per_sec": round(tokens_per_sec, 2), # <--- LA DONNÉE MANQUANTE
            "tokens_count": tokens_count,
            "total_vram_gb": round(vram, 2),
            "detected_intent": str(intention.sujet.name) if hasattr(intention, 'sujet') else "N/A"
        }

        log_benchmark_result("FULL_PIPELINE", results, prompt)
        return jsonify(results)

    except Exception as e:
        logger.error(f"Erreur Benchmark Pipeline: {e}")
        return jsonify({"error": str(e)}), 500

# ==============================================================================
# PIPELINE: PROMPT VIEWER (Version Corrigée)
# ==============================================================================
@socketio.on('connect')
def handle_prompt_viewer_connect():
    """Gère la connexion du Prompt Viewer (le seul client Socket.IO actuel)."""
    logger.info("🔍 Prompt Viewer connecté (SocketIO)")
    emit('connected', {'status': 'viewer_ready'})

@app.route('/api/last_prompt', methods=['GET'])
def get_last_prompt():
    """
    Lit le dernier prompt assemblé depuis le cache backend.
    """
    try:
        # 1. Récupérer les objets réels
        cache = get_last_prompt_cache()      # ← tu récupères le dict du cache
        lock = get_prompt_lock()             # ← tu récupères le Lock réel

        # 2. Protéger la lecture
        with lock:
            json_string = json.dumps(
                cache,
                ensure_ascii=False
            )

        # 3. Retourner
        return Response(
            json_string,
            mimetype='application/json',
            content_type='application/json; charset=utf-8'
        )

    except Exception as e:
        logger.error(f"Erreur get_last_prompt: {e}", exc_info=True)
        error_json = json.dumps({"error": str(e)}, ensure_ascii=False)
        return Response(
            error_json,
            mimetype='application/json',
            content_type='application/json; charset=utf-8',
            status=500
        )
# ==============================================================================
# Interface de chat
# ==============================================================================
# Routes spécifiques pour être sûr (optionnel mais recommandé)
@app.route('/formation_secondmind')
def serve_formation_secondmind():
    return serve_html('formation_secondmind.html')

@app.route('/formation_secondmind')
def serve_formation():
    """Sert formation_secondmind ou une page par défaut"""
    formation_path = NUCLEAR_FORMATION_DIR / "formation_secondmind.html"

    # Si le fichier existe, le servir
    if formation_path.exists():
        return send_from_directory(str(NUCLEAR_FORMATION_DIR), "formation_secondmind.html")

    # Définir les alternatives possibles
    alternatives = [
        "formation_tracke_r_parnel.html",
        "semicode-ide-interface.html"
    ]
    for alt in alternatives:
        alt_path = NUCLEAR_FORMATION_DIR / alt
        if alt_path.exists():
            logger.info(f"Utilisation de {alt} comme alternative")
            return send_from_directory(str(NUCLEAR_FORMATION_DIR), alt)

    # Si rien n'est trouvé, créer une page basique
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Formation SecondMind</title>
        <style>
            body {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                font-family: Arial, sans-serif;
                padding: 40px;
                margin: 0;
            }
            .container {
                max-width: 800px;
                margin: 0 auto;
                background: rgba(255,255,255,0.1);
                padding: 30px;
                border-radius: 20px;
                backdrop-filter: blur(10px);
            }
            h1 { text-align: center; }
            .info {
                background: rgba(255,255,255,0.2);
                padding: 20px;
                border-radius: 10px;
                margin: 20px 0;
            }
            a {
                color: #fff;
                text-decoration: underline;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎓 Formation SecondMind</h1>
            <div class="info">
                <h2>Module de Formation</h2>
                <p>Le fichier formation_secondmind.html n'a pas été trouvé.</p>
                <p>Fichiers disponibles dans le dossier :</p>
                <ul>
                    <li>formation_tracke_r_parnel.html (visible dans votre dossier)</li>
                    <li>semicode-ide-interface.html</li>
                </ul>
                <p>Pour activer ce module, renommez ou créez le fichier formation_secondmind.html</p>
            </div>
            <div class="info">
                <h2>Actions possibles :</h2>
                <p>1. Renommer formation_tracke_r_parnel.html en formation_secondmind.html</p>
                <p>2. Ou utiliser l'<a href="/interface_exploration">Interface d'Exploration</a></p>
            </div>
            <p style="text-align:center; margin-top:30px;">
                <a href="/">← Retour au Hub</a>
            </p>
        </div>
    </body>
    </html>
    """, 200

@app.route('/hub_de_secondmind')
def serve_hub_alt():
    return serve_html('hub_de_secondmind.html')

@app.route("/hub_de_secondmind.html")
def serve_hub():
    """Sert le hub depuis Nuclear_Formation_Datacenter"""
    try:
        # Vérifier dans le dossier Nuclear_Formation_Datacenter
        if (NUCLEAR_FORMATION_DIR / "hub_de_secondmind.html").exists():
            return send_from_directory(str(NUCLEAR_FORMATION_DIR), "hub_de_secondmind.html")
        else:
            logger.warning(f"Hub non trouvé dans : {NUCLEAR_FORMATION_DIR}")
            # Fallback sur formation_secondmind.html
            if (NUCLEAR_FORMATION_DIR / "formation_secondmind.html").exists():
                return send_from_directory(str(NUCLEAR_FORMATION_DIR), "formation_secondmind.html")
            else:
                return f"""
                <html>
                <body style="background: #2c2f33; color: white; padding: 50px; font-family: Arial;">
                    <h1>Erreur de configuration</h1>
                    <p>Fichiers introuvables dans : {NUCLEAR_FORMATION_DIR}</p>
                    <p>Vérifiez que les fichiers HTML sont dans le bon dossier.</p>
                </body>
                </html>
                """, 404
    except Exception as e:
        logger.error(f"Erreur serve_hub: {e}")
        return f"Erreur: {str(e)}", 500

# ==============================================================================
# Module Conversations
# ==============================================================================

class ConversationManager:
    def __init__(self, base_path: Path):
        self.base_path = base_path / "conversations"
        self.base_path.mkdir(exist_ok=True)
        self.metadata_file = self.base_path / "metadata.json"
        self._init_metadata()

    def _init_metadata(self):
        if not self.metadata_file.exists():
            # On utilise aussi la sauvegarde atomique pour les métadonnées pour être sûr
            self._sauvegarder_atomique(self.metadata_file, {
                "conversations": [],
                "folders": ["Général"]
            })

    # =========================================================================
    # 🛡️ HELPER: SAUVEGARDE ATOMIQUE (La protection contre le fichier vide)
    # =========================================================================
    def _sauvegarder_atomique(self, chemin_fichier: Path, donnees: dict):
        """
        Écrit dans un .tmp, force l'écriture disque, puis renomme.
        Empêche la création de fichiers de 0 octet en cas de crash.
        """
        chemin_temp = chemin_fichier.with_suffix('.tmp')
        try:
            with open(chemin_temp, 'w', encoding='utf-8') as f:
                json.dump(donnees, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno()) # Le secret est ici : on force Windows à écrire

            # Si on arrive ici, le fichier est intègre. On écrase l'ancien.
            chemin_temp.replace(chemin_fichier)
            return True
        except Exception as e:
            print(f"[Error] Echec sauvegarde atomique {chemin_fichier.name}: {e}")
            if chemin_temp.exists():
                try: os.remove(chemin_temp)
                except: pass
            return False

    def create_conversation(self, title: str = None, folder: str = "Général", force_id: str = None):
        # 1. LOGIQUE ID
        conv_id = force_id if force_id else str(uuid.uuid4())
        timestamp = datetime.now().isoformat()

        conversation = {
            "id": conv_id,
            "title": title or ("Brouillon" if force_id else "Nouvelle conversation"),
            "folder": folder,
            "created_at": timestamp,
            "updated_at": timestamp,
            "messages": []
        }

        conv_file = self.base_path / f"{conv_id}.json"

        # ✅ CORRECTION : Utilisation de la sauvegarde atomique
        self._sauvegarder_atomique(conv_file, conversation)

        # 2. FIX ENCODAGE ET DOUBLONS (MÉTADONNÉES)
        try:
            content = self.metadata_file.read_text(encoding='utf-8', errors='replace')
            metadata = json.loads(content)
        except Exception:
            metadata = {"conversations": []}

        # 3. GESTION INTELLIGENTE DES MÉTADONNÉES
        existe_deja = False
        for c in metadata["conversations"]:
            if c["id"] == conv_id:
                c["updated_at"] = timestamp
                existe_deja = True
                break

        if not existe_deja:
            metadata["conversations"].append({
                "id": conv_id,
                "title": conversation["title"],
                "folder": folder,
                "created_at": timestamp,
                "updated_at": timestamp
            })

        # ✅ CORRECTION : Sauvegarde atomique aussi pour les métadonnées
        self._sauvegarder_atomique(self.metadata_file, metadata)

        return conversation

    def get_conversation(self, conv_id: str):
        conv_file = self.base_path / f"{conv_id}.json"

        if not conv_file.exists():
            return None

        try:
            # ✅ Lecture sécurisée
            content = conv_file.read_text(encoding='utf-8', errors='replace')

            if not content.strip():
                print(f"[Warning] Fichier conversation vide détecté : {conv_id}.json (Ignoré)")
                # Optionnel : Supprimer le fichier vide pour ne plus avoir l'erreur ?
                # os.remove(conv_file)
                return None

            return json.loads(content)

        except Exception as e:
            print(f"[Error] Impossible de lire la conversation {conv_id}: {e}")
            return None

    def get_archive_history(self, conv_id: str) -> list:
        """Retourne l'historique formaté pour injection dans le prompt."""
        conversation = self.get_conversation(conv_id)
        if not conversation:
            return []

        history = []
        for msg in conversation.get("messages", []):
            history.append({
                "role": msg["role"],
                "content": msg["content"]
            })
        return history

    def add_message(self, conv_id: str, role: str, content: str):
        conversation = self.get_conversation(conv_id)
        if not conversation:
            return False

        conversation["messages"].append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        conversation["updated_at"] = datetime.now().isoformat()

        if len(conversation["messages"]) == 1 and conversation["title"] == "Nouvelle conversation":
            conversation["title"] = content[:50] + "..." if len(content) > 50 else content

        conv_file = self.base_path / f"{conv_id}.json"
        conv_file.write_text(json.dumps(conversation, indent=2, ensure_ascii=False))

        metadata = json.loads(self.metadata_file.read_text())
        for conv in metadata["conversations"]:
            if conv["id"] == conv_id:
                conv["title"] = conversation["title"]
                conv["updated_at"] = conversation["updated_at"]
                break
        self.metadata_file.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))

        return True

    def list_conversations(self, folder: str = None):
        try:
            # ✅ Lecture sécurisée (utf-8 + replace)
            content = self.metadata_file.read_text(encoding='utf-8', errors='replace')
            metadata = json.loads(content)
        except Exception:
            # En cas de fichier metadata corrompu, on renvoie une liste vide plutôt que de crasher
            metadata = {"conversations": []}

        conversations = metadata.get("conversations", [])

        if folder:
            conversations = [c for c in conversations if c.get("folder") == folder]

        # Tri sécurisé (gestion des clés manquantes)
        conversations.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return conversations

    def rename_conversation(self, conv_id: str, new_title: str):
        # On utilise get_conversation qui est déjà sécurisé
        conversation = self.get_conversation(conv_id)
        if not conversation:
            return False

        conversation['title'] = new_title
        conversation['updated_at'] = datetime.now().isoformat()

        conv_file = self.base_path / f"{conv_id}.json"

        # ✅ SAUVEGARDE ATOMIQUE (Fichier conversation)
        if not self._sauvegarder_atomique(conv_file, conversation):
            return False

        # Mise à jour Metadata
        try:
            content = self.metadata_file.read_text(encoding='utf-8', errors='replace')
            metadata = json.loads(content)
        except Exception:
            return False

        for conv in metadata["conversations"]:
            if conv["id"] == conv_id:
                conv["title"] = new_title
                conv["updated_at"] = conversation["updated_at"]
                break

        # ✅ SAUVEGARDE ATOMIQUE (Metadata)
        return self._sauvegarder_atomique(self.metadata_file, metadata)

    def delete_conversation(self, conv_id: str):
        conv_file = self.base_path / f"{conv_id}.json"
        if not conv_file.exists():
            return False

        trash_dir = self.base_path / "_trash"
        trash_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        trash_path = trash_dir / f"{conv_id}_{timestamp}.json"

        try:
            # Move est atomique par nature sur le même système de fichier, donc c'est OK
            shutil.move(str(conv_file), str(trash_path))
            print(f"🗑️ Conversation archivée: {trash_path.name}")
        except Exception as e:
            print(f"[Error] Erreur archivage conversation: {e}")
            return False

        # Mise à jour Metadata
        try:
            content = self.metadata_file.read_text(encoding='utf-8', errors='replace')
            metadata = json.loads(content)

            metadata["conversations"] = [c for c in metadata["conversations"] if c["id"] != conv_id]

            # ✅ SAUVEGARDE ATOMIQUE (Metadata)
            return self._sauvegarder_atomique(self.metadata_file, metadata)

        except Exception as e:
            print(f"[Error] Erreur mise à jour metadata après suppression: {e}")
            return False

# Initialiser le gestionnaire
conversation_manager = ConversationManager(MEMOIRE_DIR)


# Routes API
@app.route('/api/conversations', methods=['GET'])
def get_conversations():
    folder = request.args.get('folder')
    conversations = conversation_manager.list_conversations(folder)
    return jsonify({"conversations": conversations})

@app.route('/api/conversations', methods=['POST'])
def create_conversation():
    data = request.json
    title = data.get('title')
    folder = data.get('folder', 'Général')
    conversation = conversation_manager.create_conversation(title, folder)
    return jsonify(conversation)

@app.route('/api/conversations/<conv_id>', methods=['GET'])
def get_conversation(conv_id):
    conversation = conversation_manager.get_conversation(conv_id)
    if conversation:
        return jsonify(conversation)
    return jsonify({"error": "Conversation not found"}), 404

@app.route('/api/conversations/<conv_id>', methods=['DELETE'])
def delete_conversation(conv_id):
    if conversation_manager.delete_conversation(conv_id):
        return jsonify({"status": "success"})
    return jsonify({"error": "Conversation not found"}), 404

@app.route('/api/conversations/<conv_id>/rename', methods=['PUT'])
def rename_conversation(conv_id):
    data = request.json
    new_title = data.get('title')

    if not new_title:
        return jsonify({"error": "Title required"}), 400

    if conversation_manager.rename_conversation(conv_id, new_title):
        return jsonify({"status": "success", "title": new_title})
    return jsonify({"error": "Conversation not found"}), 404

# ==============================================================================
# ROUTE DE SYNCHRONISATION (LIVE CONTEXT)
# ==============================================================================
@app.route('/api/chat/history', methods=['GET'])
def get_active_history():
    """
    Récupère l'historique de conversation ACTIF en mémoire RAM de l'Agent.
    Version DEBUG pour inspecter le contenu.
    """
    try:
        historique = agent_semi.agent_contexte.historique_conversation

        # --- DÉBUT DEBUG ---
        print(f"\n[API DEBUG] Type de l'historique: {type(historique)}")
        print(f"[API DEBUG] Longueur de la liste: {len(historique)}")
        if len(historique) > 0:
            print(f"[API DEBUG] Dernier élément (brut): {historique[-1]}")
        else:
            print(f"[API DEBUG] L'historique est VIDE.")
        # --- FIN DEBUG ---

        formatted_history = []

        # Logique de parsing
        # Note: Si la longueur est impaire, le dernier élément est ignoré par cette boucle
        for i in range(0, len(historique), 2):
            if i + 1 < len(historique):
                user_msg = historique[i]
                bot_msg = historique[i+1]

                # Nettoyage
                if isinstance(user_msg, str) and user_msg.startswith("User:"):
                    user_msg = user_msg[5:].strip()
                if isinstance(bot_msg, str) and bot_msg.startswith("Assistant:"):
                    bot_msg = bot_msg[10:].strip()
                if isinstance(bot_msg, str) and bot_msg.startswith("Semi:"):
                    bot_msg = bot_msg[5:].strip()

                formatted_history.append({"role": "user", "content": user_msg})
                formatted_history.append({"role": "assistant", "content": bot_msg})
            else:
                # C'est ici que ça coince souvent si la liste est impaire
                print(f"[API DEBUG] Élément orphelin ignoré à l'index {i}: {historique[i]}")

        print(f"[API DEBUG] Items envoyés au front: {len(formatted_history)}")
        return jsonify({"history": formatted_history})

    except Exception as e:
        logger.error(f"Erreur récupération historique: {e}")
        return jsonify({"history": []})

# ==============================================================================
# SemiCode IDE
# ==============================================================================
@app.route('/semicode')
def semicode_interface():
    """Interface IDE SemiCode"""
    return send_from_directory(app.static_folder, "semicode_ide.html")

# Pour semicode avec le nom différent
@app.route('/semicode_ide')
def serve_semicode():
    # Rediriger vers le vrai nom du fichier
    semicode_path = NUCLEAR_FORMATION_DIR / "semicode-ide"
    if semicode_path.exists():
        return send_from_directory(str(NUCLEAR_FORMATION_DIR), "semicode-ide.html")
    else:
        return serve_html('semicode_ide.html')

@app.route('/api/list_files', methods=['GET'])
def list_files():
    """Liste tous les fichiers Python du projet"""
    try:
        files = []
        # Limiter aux dossiers principaux pour éviter la surcharge
        search_dirs = [
            AGENTIQUE_DIR / "Semi",
            AGENTIQUE_DIR / "sous_agents_gouvernes",
            AGENTIQUE_DIR / "base",
            MEMOIRE_DIR / "memoire"
        ]

        for search_dir in search_dirs:
            if search_dir.exists():
                for filepath in search_dir.rglob("*.py"):
                    relative_path = filepath.relative_to(ROOT_DIR)
                    files.append({
                        "path": str(relative_path).replace('\\', '/'),
                        "name": filepath.name,
                        "size": filepath.stat().st_size,
                        "modified": datetime.fromtimestamp(filepath.stat().st_mtime).isoformat()
                    })

        return jsonify({"files": files, "total": len(files)})
    except Exception as e:
        logger.error(f"Erreur list_files: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/read_file', methods=['POST'])
def read_file():
    """Lit le contenu d'un fichier"""
    try:
        filepath = request.json.get('path')
        if not filepath:
            return jsonify({"error": "Path required"}), 400

        full_path = ROOT_DIR / filepath

        # Sécurité : vérifier que le fichier est dans le projet
        if not str(full_path).startswith(str(ROOT_DIR)):
            return jsonify({"error": "Access denied"}), 403

        if not full_path.exists():
            return jsonify({"error": "File not found"}), 404

        content = full_path.read_text(encoding='utf-8')
        return jsonify({
            "content": content,
            "path": filepath,
            "lines": len(content.splitlines())
        })
    except Exception as e:
        logger.error(f"Erreur read_file: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/save_file', methods=['POST'])
def save_file():
    """Sauvegarde un fichier (avec backup)"""
    try:
        filepath = request.json.get('path')
        content = request.json.get('content')

        if not filepath or content is None:
            return jsonify({"error": "Path and content required"}), 400

        full_path = ROOT_DIR / filepath

        # Sécurité
        if not str(full_path).startswith(str(ROOT_DIR)):
            return jsonify({"error": "Access denied"}), 403

        # Créer un backup
        if full_path.exists():
            backup_dir = ROOT_DIR / "backups" / datetime.now().strftime('%Y%m%d')
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_path = backup_dir / f"{full_path.name}.{datetime.now().strftime('%H%M%S')}.bak"
            backup_path.write_text(full_path.read_text(encoding='utf-8'), encoding='utf-8')
            logger.info(f"Backup créé: {backup_path}")

        # Sauvegarder
        full_path.write_text(content, encoding='utf-8')

        # Si c'est un agent, déclencher une analyse
        if agent_semi and hasattr(agent_semi, 'code_extractor'):
            agent_semi.code_extractor.analyser_fichier(str(full_path))

        return jsonify({
            "success": True,
            "message": f"Fichier sauvegardé: {filepath}",
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Erreur save_file: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/execute_code', methods=['POST'])
def execute_code():
    """Exécute du code Python de façon sécurisée"""
    try:
        code = request.json.get('code', '')

        # Créer un fichier temporaire
        temp_file = ROOT_DIR / "temp" / f"exec_{datetime.now().strftime('%Y%m%d_%H%M%S')}.py"
        temp_file.parent.mkdir(exist_ok=True)
        temp_file.write_text(code, encoding='utf-8')

        # Exécuter avec timeout
        result = subprocess.run(
            [sys.executable, str(temp_file)],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(ROOT_DIR),
            check=False

        )

        # Nettoyage (Cleanup temp file - rotation not needed)
        try:
            temp_file.unlink()
        except: pass

        return jsonify({
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        })
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Execution timeout (10s)"}), 408
    except Exception as e:
        logger.error(f"Erreur execute_code: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/status', methods=['GET'])
def api_status():
    """Endpoint pour vérifier le statut du backend"""
    try:
        status_data = {
            "status": "online",
            "backend": "SecondMind",
            "timestamp": datetime.now().isoformat(),
            "version": "1.0"
        }

        # Vérifier les variables globales de manière sûre
        if 'SEMI_DISPONIBLE' in globals():
            status_data["semi_disponible"] = SEMI_DISPONIBLE
            if SEMI_DISPONIBLE and 'agent_semi' in globals():
                status_data["agent_semi_actif"] = agent_semi is not None
            else:
                status_data["agent_semi_actif"] = False
        else:
            status_data["semi_disponible"] = False
            status_data["agent_semi_actif"] = False

        # Ajouter les chemins s'ils existent
        paths = {}
        if 'ROOT_DIR' in globals():
            paths["root"] = str(ROOT_DIR)
        if 'NUCLEAR_FORMATION_DIR' in globals():
            paths["nuclear_formation"] = str(NUCLEAR_FORMATION_DIR)
        if 'MEMOIRE_DIR' in globals():
            paths["memoire"] = str(MEMOIRE_DIR)

        if paths:
            status_data["paths"] = paths

        return jsonify(status_data), 200

    except Exception as e:
        logger.error(f"Erreur dans api_status: {e}", exc_info=True)
        # Retourner quand même un statut minimal
        return jsonify({
            "status": "online",
            "backend": "SecondMind",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 200  # On retourne 200 car le backend est techniquement en ligne

@app.route('/api/list_html_files', methods=['GET'])
def list_html_files():
    """Liste tous les fichiers HTML disponibles dans Nuclear_Formation_Datacenter"""
    try:
        html_files = []

        # Parcourir le dossier principal
        for file in NUCLEAR_FORMATION_DIR.glob('*.html'):
            html_files.append({
                'name': file.name,
                'size': file.stat().st_size,
                'path': str(file)
            })

        # Aussi vérifier les fichiers Python pour info
        py_files = []
        for file in NUCLEAR_FORMATION_DIR.glob('*.py'):
            py_files.append(file.name)

        # Vérifier connect_backend_Semi aussi
        backend_files = []
        connect_dir = NUCLEAR_FORMATION_DIR / 'connect_backend_Semi'
        if connect_dir.exists():
            for file in connect_dir.glob('*.*'):
                backend_files.append(file.name)

        return jsonify({
            'html_files': html_files,
            'py_files': py_files,
            'backend_files': backend_files,
            'nuclear_formation_path': str(NUCLEAR_FORMATION_DIR),
            'files_found': len(html_files)
        })

    except Exception as e:
        logger.error(f"Erreur list_html_files: {e}")
        return jsonify({'error': str(e)}), 500

# ==============================================================================

@app.route('/<filename>')
def serve_html(filename):
    """Sert n'importe quel fichier HTML depuis Nuclear_Formation_Datacenter"""
    try:
        # Construire le chemin complet
        file_path = NUCLEAR_FORMATION_DIR / f"{filename}"

        # Log pour debug
        logger.info(f"Tentative d'ouverture : {file_path}")

        # Vérifier si le fichier existe
        if file_path.exists() and file_path.is_file():
            logger.info(f"✅ Fichier trouvé, envoi : {filename}")
            return send_from_directory(str(NUCLEAR_FORMATION_DIR), f"{filename}")
        else:
            logger.warning(f"❌ Fichier non trouvé : {file_path}")
            # Liste les fichiers disponibles pour debug
            available = [f.name for f in NUCLEAR_FORMATION_DIR.glob('*') if f.is_file() and f.suffix == '.html'] # Liste seulement les fichiers HTML
            return f"""
            <html>
            <body style="background: #2c2f33; color: white; padding: 50px; font-family: Arial;">
                <h1>Fichier non trouvé : {filename}.html</h1>
                <p>Chemin recherché : {file_path}</p>
                <h3>Fichiers HTML disponibles :</h3>
                <ul>
                    {''.join([f'<li><a href="/{f}" style="color: #7289da;">{f}</a></li>' for f in available])}
                </ul>
                <a href="/" style="color: #7289da;">Retour au Hub</a>
            </body>
            </html>
            """, 404

    except Exception as e:
        logger.error(f"Erreur serve_html pour {filename}: {e}", exc_info=True)
        return f"Erreur serveur : {str(e)}", 500

# ==============================================================================
# SECTION 2 : LOGIQUE DE LANCEMENT
# ==============================================================================

def ouvrir_navigateur():
    """
    Ouvre le navigateur UNIQUEMENT quand le serveur répond réellement.
    Évite les erreurs 404 Nginx au démarrage.
    """
    import urllib.request

    target_url = "http://127.0.0.1:3000/hub_de_secondmind"
    health_url = "http://127.0.0.1:3000/health" # On ping une route légère

    logger.info("⏳ Attente de la disponibilité du serveur (Port 3000)...")

    # On essaie pendant 10 secondes (20 tentatives de 0.5s)
    server_ready = False
    for i in range(20):
        try:
            # On teste si le serveur répond
            with urllib.request.urlopen(health_url, timeout=1) as response:
                if response.status == 200:
                    server_ready = True
                    break
        except Exception:
            # Le serveur n'est pas encore prêt, on attend un peu
            time.sleep(0.5)

    if server_ready:
        logger.info("✅ Serveur en ligne ! Ouverture du Hub.")
    else:
        logger.warning("⚠️ Timeout démarrage serveur (10s). Ouverture forcée du navigateur.")

    # On ouvre dans tous les cas (au pire l'utilisateur fera F5)
    try:
        webbrowser.open(target_url)
    except Exception as e:
        logger.warning(f"Impossible d'ouvrir le navigateur: {e}")
# ==============================================================================
# SECTION 2 : LOGIQUE DE LANCEMENT
# ==============================================================================

def ouvrir_navigateur():
    time.sleep(2)
    try:
        # CORRECTION DE L'ADRESSE IP ET AJOUT DU CHEMIN VERS LE HUB
        hub_url = "http://127.0.0.1:3000/hub_de_secondmind"
        webbrowser.open(hub_url)
        logger.info(f"🌐 Hub SecondMind ouvert à l'adresse {hub_url}.")
    except Exception as e:
        logger.warning(f"Impossible d'ouvrir le navigateur: {e}")
if __name__ == '__main__':
    logger.info("="*50)
    logger.info("🚀 Lancement du Backend SecondMind")

    # --- PARE-FEU LOGS : SOLUTION DÉFINITIVE ---
    import logging

    # 1. On définit une classe de filtre personnalisée
    class AccessLogFilter(logging.Filter):
        def filter(self, record):
            msg = record.getMessage()
            # Liste des routes à rendre muettes
            routes_ignorees = [
                '/api/status',
                '/api/stats/sync',
                '/health',
                '/api/last_prompt'
            ]
            # Si le message contient une de ces routes, on retourne False (bloquer)
            return not any(route in msg for route in routes_ignorees)

    # 2. On instancie le filtre
    my_filter = AccessLogFilter()

    # 3. On l'applique au logger Werkzeug (la source habituelle)
    logging.getLogger('werkzeug').addFilter(my_filter)

    # 4. CRITIQUE : On l'applique à tous les Handlers du Root Logger
    # C'est ce qui bloque l'affichage généré par votre logging.basicConfig() du début
    for handler in logging.root.handlers:
        handler.addFilter(my_filter)
    # ----------------------------------------------------

    try:
        gardien = GardienProjet()
        gardien.start()
        threading.Thread(target=ouvrir_navigateur, daemon=True).start()

        # Injection
        agent_semi.prompt_viewer_lock = get_prompt_lock
        if hasattr(agent_semi, 'agent_parole'):
            agent_semi.agent_parole.prompt_viewer_lock = get_prompt_lock

        init_external_routes(agent_semi)
        logger.info("✅ Routes externes ET Prompt Viewer connectés à l'agent.")

        # On garde log_output=False pour couper les logs bas niveau de SocketIO
        socketio.run(
            app,
            host='0.0.0.0',
            port=3000,
            debug=False,
            allow_unsafe_werkzeug=True,
            log_output=False
        )

    except KeyboardInterrupt:
        print("\nArrêt du serveur demandé...")
    finally:
        gardien.stop()
    logger.info("👋 Application terminée.")
