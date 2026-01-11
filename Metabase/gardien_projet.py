# Fichier : agentique/base/gardien_projet.py
import time
import json
import requests
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from pathlib import Path

PATH_TO_WATCH = "D:/rag_personnel/agentique"
# Chemin vers la map (relatif ou absolu selon ton install, ici basé sur tes paths précédents)
PROJECT_MAP_PATH = Path("D:/rag_personnel/mapping_structure/project_map.json")


class GardienHandler(FileSystemEventHandler):
    def __init__(self):
        self.whitelist_cache = set()
        self.last_map_update = 0
        # On charge la map au démarrage
        self.charger_project_map()

    def charger_project_map(self):
        """
        Charge dynamiquement la liste des fichiers à surveiller depuis project_map.json.
        """
        if not PROJECT_MAP_PATH.exists():
            print(f"⚠️ [Gardien] Map introuvable ({PROJECT_MAP_PATH}). Surveillance par défaut active.")
            # Fallback minimal si la map n'existe pas encore
            self.whitelist_cache = {"agent_Semi.py", "agent_Parole.py"}
            return

        try:
            # On ne recharge que si le fichier a changé (optimisation)
            stat = PROJECT_MAP_PATH.stat()
            if stat.st_mtime == self.last_map_update:
                return

            with open(PROJECT_MAP_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Logique flexible : supporte si la map est une liste ou un dict (architecture)
            nouveaux_fichiers = set()

            if isinstance(data, list):
                # Si c'est une liste simple de noms de fichiers
                nouveaux_fichiers = set(data)
            elif isinstance(data, dict):
                # Si c'est l'architecture (files: {...}) ou un dict plat
                root_files = data.get("files", data)
                nouveaux_fichiers = set(root_files.keys())

            self.whitelist_cache = {f for f in nouveaux_fichiers if f.endswith(".py")}
            self.last_map_update = stat.st_mtime
            print(f"🗺️ [Gardien] Project Map mise à jour : {len(self.whitelist_cache)} fichiers surveillés.")

        except Exception as e:
            print(f"❌ [Gardien] Erreur lecture Project Map : {e}")

    def on_modified(self, event):
        if event.is_directory or not event.src_path.endswith(".py"):
            return

        file_path = Path(event.src_path)

        # 1. Mise à jour map (existant)
        self.charger_project_map()

        # 2. Vérification whitelist (existant)
        if file_path.name not in self.whitelist_cache:
            return

        print(f"👁️‍🗨️  [Gardien] Modification détectée : {file_path.name}")

        # --- NOUVEAU : DÉCLENCHEMENT MISE À JOUR INDEX ---
        # On ignore les fichiers générés par l'indexation elle-même pour éviter les boucles
        if "code_chunks" not in file_path.name:
            self._lancer_reindexation_code(file_path.name)
        # -------------------------------------------------

        # 3. Audit (existant)
        self.auditer_si_necessaire(file_path)

    def _lancer_reindexation_code(self, nom_fichier):
        """Informe l'AgentCode qu'il doit rafraîchir sa vision du projet."""
        try:
            print(f"🔄 [Gardien] Demande de ré-indexation pour : {nom_fichier}")
            # Import dynamique pour éviter les cycles et charger la dernière version
            from agentique.sous_agents_gouvernes.agent_Code.agent_Code import AgentCode

            # On instancie l'agent juste pour cette tâche (Stateless worker)
            agent_code = AgentCode()
            succes = agent_code.rafraichir_index()

            if succes:
                print(f"✅ [Gardien] Index Code mis à jour avec succès.")
            else:
                print(f"⚠️ [Gardien] Échec de la mise à jour de l'index.")

        except Exception as e:
            print(f"❌ [Gardien] Erreur lors du déclenchement indexation : {e}")

    def auditer_si_necessaire(self, file_path: Path):
        """Déclenche l'audit pour les fichiers critiques"""
        if file_path.suffix == ".py" and file_path.name.startswith("agent_"):
            print(f"🕵️ [Gardien] Audit automatique : {file_path.name}")
            try:
                from agentique.sous_agents_gouvernes.agent_Auditor import AgentAuditor
                auditor = AgentAuditor()
                rapport = auditor.auditer_securite_fichier(str(file_path))

                if rapport["statut"] != "conforme":
                    print(f"⚠️ [Gardien] ALERTE : {rapport['total_erreurs']} erreur(s)")
            except Exception as e:
                print(f"❌ [Gardien] Erreur audit : {e}")

class GardienProjet:
    def __init__(self):
        self.observer = Observer()
        self.thread = None
        self.stats_thread = None
        self.running = False

    def synchroniser_stats_periodique(self):
        """Synchronise les stats via l'API backend toutes les 5 minutes"""
        # Attendre que le backend soit prêt
        time.sleep(60)

        while self.running:
            try:
                # print("📊 [Gardien] Sync stats...") # Commenté pour moins de bruit
                requests.post('http://127.0.0.1:3000/api/stats/sync', json={}, timeout=10)
            except Exception:
                pass # Silencieux si échec

            time.sleep(300)

    def start(self):
        self.running = True

        # Surveillance fichiers
        event_handler = GardienHandler()
        self.observer.schedule(event_handler, PATH_TO_WATCH, recursive=True)
        self.thread = threading.Thread(target=self.observer.start, daemon=True)
        self.thread.start()

        # Sync stats
        self.stats_thread = threading.Thread(target=self.synchroniser_stats_periodique, daemon=True)
        self.stats_thread.start()

        print("🤖 [Gardien] Service actif (Map Dynamique)")

    def stop(self):
        self.running = False
        if self.observer.is_alive():
            self.observer.stop()
            self.observer.join()
            print("🤖 [Gardien] Service arrêté.")

if __name__ == "__main__":
    # Test autonome
    g = GardienProjet()
    try:
        g.start()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        g.stop()
