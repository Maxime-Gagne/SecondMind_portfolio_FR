

{
  "timestamp": "2025-12-16T13:14:54.558085",
  "fichiers": [
    {
      "nom": "agent_Semi.py",
      "path": "agentique\\Semi\\agent_Semi.py",
      "alertes": [
        "\u26d4 Champ invalide 'instructions_manual_code' dans l'instanciation de 'ManualContextCodePrompt' (Attendus : ['intention', 'historique', 'prompt_original', 'instructions_contexte_manuel', 'regles', 'documentation', 'modificateurs', 'contexte_manuel'])",
        "\u26d4 Champ invalide 'instructions_code' dans l'instanciation de 'StandardPromptCode' (Attendus : ['instructions_code_prompt', 'intention', 'historique', 'prompt_original', 'regles', 'code_chunks', 'modificateurs', 'documentation'])"
      ]
    },
    {
      "nom": "auto_dataset_builder.py",
      "path": "agentique\\sous_agents_gouvernes\\agent_Entraineur\\auto_dataset_builder.py",
      "alertes": [
        "\ud83d\udd75\ufe0f DETECT\u00c9 dans assignation de 'nouvelle_donnee' : Utilisation d'un dictionnaire manuel qui imite le contrat 'ResultatIntention'.\n   -> Cl\u00e9s suspectes : ['action', 'prompt', 'categorie', 'sujet']\n   -> Conseil : Instanciez directement 'ResultatIntention(...)'."
      ]
    },
    {
      "nom": "traitement_brute_persistante.py",
      "path": "agentique\\sous_agents_gouvernes\\agent_Memoire\\traitement_brute_persistante.py",
      "alertes": [
        "\ud83d\udd75\ufe0f DETECT\u00c9 dans assignation de 'meta' : Utilisation d'un dictionnaire manuel qui imite le contrat 'ResultatIntention'.\n   -> Cl\u00e9s suspectes : ['action', 'categorie', 'sujet']\n   -> Conseil : Instanciez directement 'ResultatIntention(...)'."
      ]
    },
    {
      "nom": "agent_Recherche.py",
      "path": "agentique\\sous_agents_gouvernes\\agent_Recherche\\agent_Recherche.py",
      "alertes": [
        "\u26a0\ufe0f HYGI\u00c8NE 'recherche_hybride_vectorielle' : Variables mortes -> ['elapsed']"
      ]
    },
    {
      "nom": "SUPERVISION_FLUX",
      "path": "SYSTEM",
      "alertes": [
        "\ud83d\udcc9 FUITE DE DONN\u00c9ES D\u00c9TECT\u00c9E : Le LLM a g\u00e9n\u00e9r\u00e9 6 fois, mais la m\u00e9moire brute n'a stock\u00e9 que 5 fois (Delta: 1)."
      ]
    }
  ]
}
