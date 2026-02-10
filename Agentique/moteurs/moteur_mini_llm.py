#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MoteurMiniLLM — Version Client HTTP (llama-server)
Dédié aux tâches rapides (Classification, Juge, Résumé)
"""

import yaml
import requests
import json
import threading
from pathlib import Path
from typing import Dict, Generator, Any

from agentique.base.META_agent import AgentBase

class MoteurMiniLLM(AgentBase):
    """
    Client HTTP pour le Mini-LLM (ex: Phi-3 sur port 8081).
    Singleton conservé pour la gestion du Lock inter-threads.
    """

    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, config_file: str = "config_moteur_mini_llm.yaml"):
        if MoteurMiniLLM._initialized:
            return

        super().__init__(nom_agent="MoteurMiniLLM")

        # 🔒 VERROU THREAD-SAFETY
        # Empêche l'Agent Juge et l'Agent Principal de parler au MiniLLM
        # exactement à la même milliseconde côté client Python.
        self.lock = threading.Lock()

        # --- 1. CHARGEMENT CONFIG ---
        cfg_path = Path(__file__).parent / config_file
        # Fallback chemin absolu si nécessaire
        if not cfg_path.exists():
             # Tu pourras ajuster ce chemin selon ton arborescence réelle
             cfg_path = Path("D:/rag_personnel/agentique/sous_agents_gouvernes/agent_Parole/moteurs/config_moteur_mini_llm.yaml")

        if not cfg_path.exists():
            raise FileNotFoundError(f"❌ Fichier config introuvable : {cfg_path}")

        with open(cfg_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        # Récupération du profil
        self.active_profile = self.config.get("active_profile_mini_llm", "phi3_mini_server")
        if self.active_profile not in self.config["models"]:
            raise ValueError(f"❌ Profil '{self.active_profile}' introuvable.")

        self.model_cfg = self.config["models"][self.active_profile]

        # Configuration URL
        self.server_url = self.model_cfg.get("server_url")
        if not self.server_url:
            raise ValueError(f"❌ URL manquante pour le profil {self.active_profile}")

        # Test Connexion
        try:
            requests.get(f"{self.server_url}/health", timeout=2)
            self.logger.info(f"✅ Mini-LLM connecté sur {self.server_url}")
        except Exception:
            self.logger.log_warning(f"⚠️ Mini-LLM ne répond pas sur {self.server_url}. Vérifier le lancement du serveur.")

        self.backend = "llama_server_http"
        MoteurMiniLLM._initialized = True

    def _prepare_payload(self, prompt: str, temperature: float = None, stream: bool = False) -> dict:
        """Prépare le payload en utilisant exclusivement la configuration YAML."""
        gen_cfg = self.model_cfg.get("generation", {})

        # Température : priorité à l'argument, puis au YAML, puis fallback
        temp = temperature if temperature is not None else gen_cfg.get("temperature", 0.1)

        # Nettoyage des stop tokens depuis le YAML
        raw_stop = gen_cfg.get("stop_tokens", ["<|im_end|>", "</s>"])
        if not isinstance(raw_stop, list):
            raw_stop = [raw_stop] if isinstance(raw_stop, str) else ["<|im_end|>", "</s>"]
        clean_stop = [str(s) for s in raw_stop if s]

        return {
            "prompt": prompt,
            "stream": stream,
            "n_predict": int(gen_cfg.get("max_tokens", 512)),
            "temperature": float(temp),
            "top_p": float(gen_cfg.get("top_p", 0.9)),
            "stop": clean_stop,
            "cache_prompt": gen_cfg.get("cache_prompt", False), # Source: YAML
            "do_sample": gen_cfg.get("do_sample", False)        # Source: YAML
        }

    # ==========================================================
    # 🚀 GÉNÉRATION STREAMING
    # ==========================================================
    def generer_stream(self, prompt: str, temperature: float = None) -> Generator[str, None, None]:
        """Génération streaming avec arrêt forcé sur stop_tokens."""
        payload = self._prepare_payload(prompt, temperature, stream=True)
        stop_tokens = payload.get("stop", [])

        with self.lock:
            try:
                response = requests.post(
                    f"{self.server_url}/completion",
                    json=payload,
                    stream=True,
                    timeout=60
                )
                response.raise_for_status()

                for line in response.iter_lines():
                    if line:
                        line_str = line.decode('utf-8')
                        if line_str.startswith('data: '):
                            data_str = line_str[6:]
                            if data_str.strip() == '[DONE]':
                                break
                            try:
                                data = json.loads(data_str)
                                if 'content' in data:
                                    token = data['content']
                                    # Frein d'urgence si le serveur dépasse le stop token
                                    if any(s in token for s in stop_tokens):
                                        break
                                    yield token
                            except json.JSONDecodeError:
                                continue
            except Exception as e:
                self.logger.log_error(f"Erreur Streaming MiniLLM: {e}")
                yield ""

    # ==========================================================
    # 🚀 GÉNÉRATION SIMPLE (Non-Streaming)
    # ==========================================================
    def generer(self, prompt: str, temperature: float = None) -> Dict[str, Any]:
        payload = self._prepare_payload(prompt, temperature, stream=False)

        with self.lock: # Protection Thread-Safe
            try:
                response = requests.post(
                    f"{self.server_url}/completion",
                    json=payload,
                    timeout=60
                )
                response.raise_for_status()
                return {"response": response.json().get("content", "")}
            except Exception as e:
                self.logger.log_error(f"Erreur MiniLLM: {e}")
                return {"error": str(e)}

    @property
    def is_lora(self) -> bool:
        return False
