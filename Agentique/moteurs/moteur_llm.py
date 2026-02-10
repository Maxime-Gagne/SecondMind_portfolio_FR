#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MoteurLLM - Version HTTP Client (llama-server)
Source de vérité unique : config_moteurllm.yaml
"""

import json
import yaml
import requests
from pathlib import Path
from typing import Generator, Dict, List
from agentique.base.META_agent import AgentBase

class MoteurLLM(AgentBase):
    def __init__(self, perf_monitor=None):
        super().__init__(nom_agent="MoteurLLM")
        self.perf_monitor = perf_monitor

        # 1. Chargement Config
        self.config = self._load_config()
        active_profile = self.config.get('active_profile')

        if not active_profile or active_profile not in self.config["models"]:
            raise ValueError(f"❌ CONFIG: Profil '{active_profile}' invalide.")

        self.active_profile = active_profile
        self.model_config = self.config["models"][active_profile]

        # 2. Configuration Serveur (Source: YAML)
        self.server_url = self.model_config.get("server_url")
        if not self.server_url:
             raise ValueError(f"❌ CONFIG: 'server_url' manquant pour le profil {active_profile}")

        # 3. Test connexion
        try:
            health = requests.get(f"{self.server_url}/health", timeout=2)
            if health.status_code == 200:
                self.logger.info(f"✅ Connecté au serveur llama-server sur {self.server_url}")
            else:
                self.logger.log_warning("⚠️ Serveur répond mais status health != 200")
        except requests.exceptions.ConnectionError:
            raise RuntimeError(
                f"❌ Serveur inaccessible sur {self.server_url}. \n"
                f"Vérifie que llama-server est bien lancé."
            )

        self.backend = "llama_server_http"

    def _load_config(self):
        """Charge le fichier YAML comme source de vérité unique."""
        self.config_path = Path(__file__).parent / "config_moteurllm.yaml"
        if not self.config_path.exists():
            # Chemin absolu de secours si nécessaire
            self.config_path = Path("D:/rag_personnel/agentique/sous_agents_gouvernes/agent_Parole/moteurs/config_moteurllm.yaml")

        if not self.config_path.exists():
            raise FileNotFoundError(f"❌ Config introuvable au chemin : {self.config_path}")

        with open(self.config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _prepare_payload(self, prompt_text: str, stream: bool = False) -> dict:
        """Prépare les paramètres de génération en utilisant exclusivement le YAML."""
        gen_cfg = self.model_config.get("generation", {})

        # Nettoyage et sécurisation des stop tokens issus du YAML
        raw_stop = gen_cfg.get("stop_tokens", ["<|im_end|>", "</s>"])
        if not isinstance(raw_stop, list):
            raw_stop = [raw_stop] if isinstance(raw_stop, str) else ["<|im_end|>", "</s>"]
        clean_stop = [str(s) for s in raw_stop if s]

        # Construction du payload dynamique
        return {
            "prompt": prompt_text,
            "stream": stream,
            "n_predict": int(gen_cfg.get("max_tokens", 1024)),
            "temperature": float(gen_cfg.get("temperature", 0.7)),
            "top_p": float(gen_cfg.get("top_p", 0.9)),
            "stop": clean_stop,
            "cache_prompt": gen_cfg.get("cache_prompt", True), # Lu depuis YAML
            "do_sample": gen_cfg.get("do_sample", False)       # Lu depuis YAML
        }

    def generer_stream(self, prompt_text: str) -> Generator[str, None, None]:
        """Génération en mode streaming avec gestion d'erreur robuste."""
        if not prompt_text:
            yield "[ERREUR: Prompt vide]"
            return

        payload = self._prepare_payload(prompt_text, stream=True)
        stop_tokens = payload.get("stop", [])

        try:
            response = requests.post(
                f"{self.server_url}/completion",
                json=payload,
                stream=True,
                timeout=300
            )

            if response.status_code == 400:
                error_msg = response.text
                self.logger.log_error(f"❌ REQUÊTE REJETÉE (400). Payload : {json.dumps(payload)}")
                yield f"[ERREUR 400: {error_msg}]"
                return

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
                                # Frein d'urgence local pour les stop tokens
                                if any(s in token for s in stop_tokens):
                                    break
                                yield token
                        except json.JSONDecodeError:
                            continue

        except Exception as e:
            self.logger.log_error(f"Erreur streaming critique: {e}")
            yield f"[ERREUR CRITIQUE: {e}]"

    def generer(self, prompt_text: str) -> Dict:
        """Génération standard (non-streamée)."""
        payload = self._prepare_payload(prompt_text, stream=False)
        try:
            response = requests.post(
                f"{self.server_url}/completion",
                json=payload,
                timeout=300
            )
            response.raise_for_status()
            data = response.json()

            content = data.get("content", "")
            # Nettoyage post-génération si nécessaire
            for s in payload.get("stop", []):
                if s in content:
                    content = content.split(s)[0]

            return {"response": content}

        except Exception as e:
            self.logger.log_error(f"Erreur génération: {e}")
            return {"error": str(e)}

    @property
    def is_lora(self) -> bool:
        return "lora" in self.active_profile.lower()
