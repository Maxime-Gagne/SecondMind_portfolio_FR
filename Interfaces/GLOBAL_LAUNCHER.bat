@echo off
:: ==========================================
:: 🚀 GLOBAL LAUNCHER SECONDMIND (4 Onglets)
:: ==========================================
chcp 65001 > nul
title PREPARATION DU LANCEMENT...

:: --- 1. CONFIGURATION DES CHEMINS ---
set "ROOT=D:\rag_personnel"
set "SERVER_EXE=%ROOT%\llama_cpp_server\llama-server.exe"
set "ENV_ACTIVATE=%ROOT%\rag_env\Scripts\activate.bat"

:: Modèles
set "MODEL_MAIN=%ROOT%\model\qwen2.5-coder-14b-instruct-q4_k_m.gguf"
set "MODEL_MINI=%ROOT%\model\Phi-3-mini-4k-instruct-q4.gguf"

:: Dossiers Python
set "DIR_DOC=%ROOT%\memoire\connaissances\documentation_technique"
set "DIR_BACKEND=%ROOT%\Nuclear_Formation_Datacenter\connect_backend_Semi"

:: --- 2. CONSTRUCTION DE LA COMMANDE WINDOWS TERMINAL ---
:: Note : J'ai remplace les Emojis par des balises [TEXTE] pour eviter les bugs d'affichage.

echo Lancement de l'ecosysteme complet...

start wt ^
    --window 0 --title "[MAIN] Qwen 14B" cmd /k "%SERVER_EXE% -m %MODEL_MAIN% -c 32768 -ngl -1 -ctk q8_0 -ctv q8_0 -fa on --port 8080" ^
    ; ^
    new-tab --title "[MINI] Phi-3" cmd /k "%SERVER_EXE% -m %MODEL_MINI% -c 4096 -ngl -1 --port 8081" ^
    ; ^
    new-tab --title "[DOCS] Server" -d "%DIR_DOC%" cmd /k "%ENV_ACTIVATE% && python doc_viewer_server.py" ^
    ; ^
    new-tab --title "[BRAIN] Backend" -d "%DIR_BACKEND%" cmd /k "%ENV_ACTIVATE% && python interface_backend_hermes.py"

:: Fermeture du lanceur
exit