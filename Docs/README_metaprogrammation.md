# ⚙️ Métaprogrammation — Zéro Boilerplate

## Comment une Métaclasse Instrumente 10 Agents Automatiquement

---

## Le Problème

Dans un système multi-agents, chaque agent a besoin des mêmes outils de base :
- Un **logger** pour tracer ses actions
- Un **stats_manager** pour compter ses appels et erreurs
- Un **auditor** pour valider ses chemins et échanges
- Une **mémoire RAM** partagée pour le contexte de travail

L'approche naïve : copier-coller ce code d'initialisation dans chaque agent.

```python
# ❌ Sans métaclasse — Code répété 10 fois
class AgentRecherche:
    def __init__(self):
        self.logger = CognitiveLogger("Recherche", ...)
        self.stats_manager = StatsBase("Recherche")
        self.auditor = AuditorBase("recherche")
        self.memoire_ram = MemoireTravailRAM()
        # ... le vrai code de l'agent
```

**Résultat** : 40+ lignes de boilerplate par agent. Risque d'oubli. Maintenance cauchemardesque.

---

## L'Insight

Et si la **classe elle-même** pouvait s'auto-configurer au moment de sa création ?

Python permet de contrôler *comment* une classe est instanciée via les **métaclasses**. Au lieu d'écrire le boilerplate, on le génère.

---

## La Solution : MetaAgent

### Architecture

```python
class MetaAgent(type):
    """Métaclasse qui injecte les outils ET le monitoring automatique."""

    def __call__(cls, *args, **kwargs):
        # 1. Création de l'instance standard
        instance = cls.__new__(cls)

        # 2. Identification automatique
        nom_agent_display = cls.__name__.replace("Agent", "")
        nom_agent_audit = nom_agent_display.lower()

        # 3. Injection des composants (ordre strict)
        instance.memoire_ram = MemoireTravailRAM()
        instance.stats_manager = StatsBase(nom_agent_display)
        instance.auditor = AuditorBase(nom_agent_audit)
        instance.logger = CognitiveLogger(
            nom_agent=nom_agent_display,
            auditor=instance.auditor,
            console_output=True
        )

        # 4. Auto-instrumentation des méthodes
        for attr_name in dir(cls):
            if not attr_name.startswith("_") and callable(getattr(cls, attr_name)):
                original_method = getattr(cls, attr_name)
                decorated_method = MetaAgent._creer_wrapper_stats(
                    instance, original_method, attr_name
                )
                setattr(instance, attr_name, decorated_method)

        # 5. Initialisation standard
        cls.__init__(instance, *args, **kwargs)

        return instance
```

### Utilisation — Une Ligne Suffit

```python
# ✅ Avec métaclasse — L'agent hérite, c'est tout
class AgentRecherche(AgentBase):
    def __init__(self):
        super().__init__(nom_agent="AgentRecherche")
        # Le vrai code métier, sans boilerplate

    def recherche_hybride(self, query: str):
        # self.logger, self.auditor, self.stats_manager
        # sont déjà disponibles et configurés
        self.logger.info(f"Recherche: {query}")
        ...
```

**10 agents × 40 lignes économisées = 400 lignes de code éliminées.**

---

## Auto-Instrumentation : Le Monitoring Invisible

La métaclasse ne se contente pas d'injecter des outils. Elle **wrappe automatiquement chaque méthode publique** pour collecter des métriques.

### Le Wrapper de Stats

```python
@staticmethod
def _creer_wrapper_stats(instance, method, method_name):
    """Crée un wrapper qui loggue les appels et erreurs automatiquement."""

    @functools.wraps(method)
    def wrapper(*method_args, **method_kwargs):
        # Compteur d'appels global
        instance.stats_manager.incrementer_appel()

        # Compteur spécifique à la méthode
        instance.stats_manager.incrementer_stat_specifique(f"appels_{method_name}")

        start_time = time.perf_counter()
        succes = False

        try:
            result = method(instance, *method_args, **method_kwargs)
            succes = True
            return result

        except Exception as e:
            instance.stats_manager.incrementer_erreur()
            instance.stats_manager.incrementer_stat_specifique(f"erreurs_{method_name}")
            raise e

        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            instance.auditor.enregistrer_stat(method_name, {
                "succes": succes,
                "duree_ms": duration_ms
            })

    return wrapper
```

### Ce que ça donne concrètement

Sans écrire une seule ligne de monitoring, chaque agent produit automatiquement :

```json
{
  "AgentRecherche": {
    "appels_totaux": 847,
    "erreurs_totales": 3,
    "appels_recherche_hybride": 412,
    "appels_recherche_vectorielle": 298,
    "erreurs_recherche_hybride": 1,
    "duree_moyenne_ms": 82.4
  }
}
```

**Le développeur écrit le métier. La métaclasse écrit l'observabilité.**

---

## Singleton pour la Mémoire Partagée

La `MemoireTravailRAM` utilise le pattern Singleton pour garantir que tous les agents partagent le même espace de travail :

```python
class MemoireTravailRAM:
    """Mémoire RAM partagée entre tous les agents."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.memoire_ram = []
            cls._instance.stats = {
                "items_travail_ajoutes": 0,
                "items_evalues": 0,
                "items_valides": 0,
                "items_rejetes": 0,
                "items_remplaces": 0
            }
        return cls._instance
```

Quand `AgentContexte` ajoute un item de travail, `AgentJuge` peut immédiatement y accéder — sans passer par un bus de messages ou une base de données.

---

## Bénéfices Concrets

| Aspect | Sans Métaclasse | Avec MetaAgent |
|--------|-----------------|----------------|
| Lignes de boilerplate | ~40 par agent | 0 |
| Risque d'oubli (logger, stats) | Élevé | Impossible |
| Ajout d'un nouvel agent | Copier-coller + adapter | Hériter d'AgentBase |
| Monitoring des méthodes | Manuel, méthode par méthode | Automatique, exhaustif |
| Cohérence des noms de stats | Variable | Garantie par convention |

---

## Pourquoi C'est Avancé

La métaprogrammation Python est rarement utilisée à ce niveau en production. Ce code démontre :

1. **Compréhension du modèle objet Python** — `__new__` vs `__init__`, `type.__call__`
2. **Décorateurs dynamiques** — wrapping de méthodes à l'instanciation, pas à la définition
3. **Monkey patching propre** — `functools.wraps` pour préserver les signatures
4. **Patterns de conception** — Singleton, Injection de dépendances, Aspect-Oriented Programming

Ce n'est pas du code "clever pour être clever". C'est une solution pragmatique à un problème réel de maintenance dans un système à 10+ agents.

---

## Fichiers Clés

- `META_agent.py` — Métaclasse MetaAgent + classe AgentBase
- `auditor_base.py` — AuditorBase injecté (chemins, validation)
- `contrats_interface.py` — StatsBase injecté (compteurs)
- `cognitive_logger.py` — CognitiveLogger injecté (traces)

---

*Maxime Gagné — Architecte Cognitif — SecondMind*
