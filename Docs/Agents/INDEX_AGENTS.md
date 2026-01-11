# 🗂️ Index des Agents du Système SecondMind

Ce document répertorie l'ensemble des agents actifs du système, classés par rôle stratégique. Chaque agent dispose de son propre fichier `README.md` détaillé dans son répertoire respectif.

---
# L'agent officiel SecondMind
AgentSemi (**SE**cond**MI**nd) est l'orchestrateur du pipeline et assistant officiel de SecondMind [Consulter](./README_agent_Semi.md)

## 🧠 Agents Cognitifs (Pensée & Contexte)
*Agents responsables de la structuration de la réflexion et de la préparation du contexte.*

| Agent             | Responsabilité Primaire                                                                          | README                                  |
| :---------------- | :----------------------------------------------------------------------------------------------- | :-------------------------------------- |
| **AgentContexte** | Orchestrer la récupération et le filtrage intelligent du contexte (mémoire, règles, historique). | [Consulter](./README_agent_Contexte.md) |
| **AgentParole**   | Construire le prompt ChatML final en assemblant les variables système et le profil utilisateur.  | [Consulter](./README_agent_Parole.md)   |
| **AgentReflexor** | Analyser les incidents et feedbacks pour assurer l'auto-correction comportementale.              | [Consulter](./README_agent_Reflexor.md) |

---

## ⚙️ Agents Exécutifs (Action & Données)
*Agents responsables de l'exécution technique et de la manipulation des données.*

| Agent              | Responsabilité Primaire                                                                 | README                                   |
| :----------------- | :-------------------------------------------------------------------------------------- | :--------------------------------------- |
| **AgentCode**      | Orchestrer l'accès à l'intelligence du code source via recherche hybride et indexation. | [Consulter](./README_agent_Code.md)      |
| **AgentRecherche** | Localiser et extraire l'information (mémoire, code, web) avec performance instantanée.  | [Consulter](./README_agent_Recherche.md) |
| **AgentMemoire**   | Gérer le cycle de vie de la mémoire persistante (capture, stockage et indexation).      | [Consulter](./README_agent_Memoire.md)   |

---

## ⚖️ Agents de Gouvernance (Contrôle & Qualité)
*Agents responsables de la sécurité, de la conformité et de la validation.*

| Agent            | Responsabilité Primaire                                                               | README                                 |
| :--------------- | :------------------------------------------------------------------------------------ | :------------------------------------- |
| **AgentAuditor** | Garantir l'intégrité technique, la sécurité du code et la conformité des contrats.    | [Consulter](./README_agent_Auditor.md) |
| **AgentJuge**    | Arbitre impitoyable de la pertinence (RAG) et de la cohérence factuelle des réponses. | [Consulter](./README_agent_Juge.md)    |

---

## 🛠️ Agents de Support (Apprentissage)
*Agents responsables de la maintenance des capacités du système.*

| Agent               | Responsabilité Primaire                                                      | README                                    |
| :------------------ | :--------------------------------------------------------------------------- | :---------------------------------------- |
| **AgentEntraineur** | Superviser l'apprentissage SBERT et entraîner les classifieurs d'intentions. | [Consulter](./README_agent_Entraineur.md) |

---


