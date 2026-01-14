#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import json
import uuid
from pathlib import Path
from datetime import datetime
import logging


class CognitiveLogger:
    def __init__(self, nom_agent=None, session_id=None, console_output=True, auditor=None):
        """
        CORRECTION: Utiliser l'auditor pour obtenir les chemins de logs
        """
        
        self.session_id = session_id if session_id else str(uuid.uuid4())
        self.nom_agent = nom_agent or "Unknown"
        self.console_output = console_output
        self.auditor = auditor
        
        # CORRECTION: Utiliser l'auditor pour obtenir le chemin des logs
        if self.auditor:
            try:
                logs_path = self.auditor.get_path("logs")
                if logs_path:
                    self.log_dir = Path(logs_path)
                    self.log_file = self.log_dir / f"session_{self.session_id}.jsonl"
                    
                    # Vérifier si le dossier existe
                    if not self.log_dir.exists():
                        if self.console_output:
                            print(f"⚠️ [{self.nom_agent}] Le répertoire de logs '{self.log_dir}' n'existe pas. Le logging vers fichier sera désactivé.")
                        self.log_file = None
                else:
                    if self.console_output:
                        print(f"⚠️ [{self.nom_agent}] Aucun chemin de logs trouvé via l'auditor. Le logging vers fichier sera désactivé.")
                    self.log_file = None
                    self.log_dir = None
            except Exception as e:
                if self.console_output:
                    print(f"⚠️ [{self.nom_agent}] Erreur lors de l'obtention du chemin via auditor: {e}")
                self.log_file = None
                self.log_dir = None
        else:
            # FALLBACK: Si pas d'auditor, utiliser un chemin par défaut
            self.log_dir = Path("logs")
            if not self.log_dir.exists():
                if self.console_output:
                    print(f"⚠️ [{self.nom_agent}] Pas d'auditor fourni et le dossier 'logs' n'existe pas. Le logging vers fichier sera désactivé.")
                self.log_file = None
            else:
                self.log_file = self.log_dir / f"session_{self.session_id}.jsonl"

        # Configurer le logger standard Python pour éviter les conflits
        self.std_logger = logging.getLogger(f"CognitiveLogger.{self.nom_agent}.{self.session_id}")
        self.std_logger.setLevel(logging.DEBUG)
        self.std_logger.propagate = False
        
        # Éviter la duplication des handlers
        if not self.std_logger.handlers:
            # Handler console
            if self.console_output:
                console_handler = logging.StreamHandler()
                console_handler.setLevel(logging.INFO)
                formatter = logging.Formatter('[%(name)s] %(levelname)s: [%(message)s]')
                console_handler.setFormatter(formatter)
                self.std_logger.addHandler(console_handler)
            
            # Handler fichier (seulement si le fichier de log existe)
            if self.log_file and self.log_dir and self.log_dir.exists():
                try:
                    file_handler = logging.FileHandler(self.log_file, encoding='utf-8')
                    file_handler.setLevel(logging.DEBUG)
                    file_formatter = logging.Formatter('[%(asctime)s] [%(name)s] %(levelname)s: %(message)s')
                    file_handler.setFormatter(file_formatter)
                    self.std_logger.addHandler(file_handler)
                except Exception as e:
                    if self.console_output:
                        print(f"⚠️ [{self.nom_agent}] Impossible de créer le handler fichier: {e}")

    def _log_to_handlers(self, level, console_msg, json_msg, exc_info=False):
        """
        CORRECTION: Gestion propre des logs avec le logger standard Python
        """
        # Log vers la console et fichier via le logger standard
        log_method = getattr(self.std_logger, level.lower(), self.std_logger.info)
        
        try:
            if exc_info:
                log_method(console_msg, exc_info=True)
            else:
                log_method(console_msg)
        except Exception as e:
            # En cas d'erreur avec le logger standard, fallback vers print
            if self.console_output:
                print(f"[LOGGER ERROR] {console_msg}")
                if exc_info:
                    import traceback
                    traceback.print_exc()

        # Log vers le fichier JSON (si disponible)
        if self.log_file and self.log_dir and self.log_dir.exists():
            try:
                with open(self.log_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(json_msg, ensure_ascii=False) + "\n")
            except Exception as e:
                if self.console_output:
                    print(f"[LOGGER ERROR] Impossible d'écrire dans {self.log_file}: {e}")

    def log_interaction(self, role, message, context="main"):
        entry = {
            "timestamp": self._now(),
            "type": "interaction",
            "role": role,
            "message": message,
            "context": context,
            "agent": self.nom_agent
        }
        
        console_msg = f"[{self.nom_agent}] INTERACTION: [{role}] {message}"
        self._log_to_handlers("INFO", console_msg, entry)

    def log_api_call(self, engine, prompt, response_json):
        entry = {
            "timestamp": self._now(),
            "type": "api_call",
            "engine": engine,
            "prompt": prompt,
            "raw_response": response_json,
            "agent": self.nom_agent
        }
        
        console_msg = f"[{self.nom_agent}] API_CALL: {engine}"
        self._log_to_handlers("INFO", console_msg, entry)

    def log_thought(self, thought_text):
        entry = {
            "timestamp": self._now(), 
            "type": "thought", 
            "content": thought_text,
            "agent": self.nom_agent
        }
        
        console_msg = f"[{self.nom_agent}] 🧠 THOUGHT: {thought_text}"
        self._log_to_handlers("INFO", console_msg, entry)

    def log_error(self, error_msg, exc_info=False):
        entry = {
            "timestamp": self._now(), 
            "type": "error", 
            "message": error_msg,
            "agent": self.nom_agent
        }
        
        console_msg = f"[{self.nom_agent}] ERROR: {error_msg}"
        self._log_to_handlers("ERROR", console_msg, entry, exc_info=exc_info)

    def log_warning(self, warning_msg):
        """Méthode ajoutée pour la compatibilité"""
        entry = {
            "timestamp": self._now(), 
            "type": "warning", 
            "message": warning_msg,
            "agent": self.nom_agent
        }
        
        console_msg = f"[{self.nom_agent}] WARNING: {warning_msg}"
        self._log_to_handlers("WARNING", console_msg, entry)
    
    def info(self, message):
        """Compatibilité avec logging standard"""
        entry = {
            "timestamp": self._now(),
            "type": "info",
            "message": message,
            "agent": self.nom_agent
        }
        
        console_msg = f"[{self.nom_agent}] INFO: {message}"
        self._log_to_handlers("INFO", console_msg, entry)

    def _now(self):
        return datetime.now().isoformat()

    def set_correlation_id(self):
        """Génère un ID de corrélation unique"""
        return str(uuid.uuid4())[:8]

    def signal_gouvernance(self, message: str):
        """
        Log un événement de gouvernance de haute priorité (ex: '!!!').
        Nous utilisons log_error en interne pour lui donner une haute visibilité.
        """
        # On utilise log_error car on sait qu'elle existe et qu'elle a
        # le bon niveau de visibilité (CRITICAL/ERROR)
        self.log_error(f"🚨 [GOUVERNANCE] {message}")