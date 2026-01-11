# 🧪 Stratégie de Test & Validation Continue

> **Philosophie** : "On ne teste pas le chaos du LLM, on teste la robustesse de la structure qui l'encadre."

Pour garantir la stabilité du système **SecondMind**, j'ai adopté une stratégie de test qui découple totalement la logique d'orchestration de l'inférence neuronale.

---

## 1. Architecture des Tests : Co-localisation & Isolation

Contrairement aux conventions classiques (dossier `/tests` séparé), j'ai opté pour une **co-localisation stricte**.

* **Proximité Immédiate** : Chaque agent critique dispose de son miroir de test dans le même répertoire.
    * `agentique/agent_Parole.py` ↔ `agentique/agent_Parole_UNITTEST.py`
    * `agentique/agent_Juge.py` ↔ `agentique/agent_Juge_UNITTEST.py`
* **Maintenance Atomique** : Cette structure impose visuellement au développeur de considérer le test comme une extension indissociable du code source.

---

## 2. **La Validation Profonde**

Les tests unitaires ne se contentent pas de vérifier si le code "ne plante pas". Ils valident la conformité stricte aux **Contrats d'Interface** via l'`AuditorBase`.

### **Le Problème**
En Python dynamique, une fonction peut retourner un dictionnaire `{ "score": 0.5 }` alors qu'on attendait un objet `ResultatJuge(score=0.5)`. Le code continue de tourner, mais la structure s'effrite silencieusement.

### **La Solution SecondMind**
J'ai implémenté des assertions récursives (`assert_validation_profonde`) qui inspectent la structure des données retournées :
1.  **Typage Strict** : Vérifie que l'objet est bien une `Dataclass` et non un `dict`.
2.  **Inspection Récursive** : Si l'objet contient une liste (ex: `List[ItemComplexe]`), le test itère sur chaque élément pour valider son type.
3.  **Fail-Fast** : Le test échoue immédiatement si un seul champ "ignorant" ou "vide" est détecté là où il ne devrait pas l'être.

---

## 3. **Mocking Déterministe & Simulation LLM**
Pour tester la logique métier (prompts, parsing, routing) sans dépendre du GPU ni payer le coût de latence, tous les appels LLM sont mockés.
- Simulation de Comportement : J'utilise unittest.mock.MagicMock pour simuler les réponses du moteur.
- Scénarios de Crise : Les tests injectent volontairement des réponses "cassées" (JSON malformé, hallucination, refus) pour vérifier la résilience de l'agent.

**Cas d'usage : Test de l'AgentJuge**
On ne demande pas au vrai LLM de juger. On injecte une réponse simulée et on vérifie que l'AgentJuge réagit correctement.
Scénario Testé,Injection (Mock LLM),Résultat Attendu
Nominal,"JSON Valide {""score"": 1.0}",Objet ResultatJuge propre.
Bruité,Texte bavard + JSON,Extraction regex + Parsing réussi.
Halluciné,JSON invalide,Déclenchement Retry ou Erreur formatée.

---

## 4. **Tests des Prompts (Prompt Engineering Unit Testing)**
Avant même d'envoyer une requête au modèle, le système doit garantir que le prompt construit est parfait.
- Vérification d'Assemblage : Les tests de AgentParole vérifient que le prompt final contient bien tous les blocs dynamiques (Contexte, Règles, Historique) dans le bon ordre.
- Protection contre l'Amnésie : Un test spécifique valide que les "Souvenirs Vectoriels" sont bien injectés dans la section système du prompt ChatML.

---

## 5. **Bilan**
Cette stratégie transforme un développement IA souvent "expérimental" en un processus d'ingénierie logicielle rigoureux.
- Couverture : 100% de la logique d'orchestration est validée.
- Déterminisme : Les tests passent toujours (ou échouent toujours) pour la même raison, éliminant les "flaky tests" liés à l'IA.
- Sécurité : Aucun code ne part en production si les contrats de données ne sont pas validés récursivement.


