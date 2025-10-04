# IA Auto‑Évolutive : Prototype

Ce prototype vous fournit une base pour une **IA auto‑évolutive** qui apprend en explorant des documents textuels et qui s'améliore en fonction des résultats.

## Fonctionnement général

1. **Ingestion et indexation** : le script `main.py` charge un jeu de documents factices (`dummy_data.json`), les transforme en représentations numériques simples et construit un index de recherche.
2. **Réponses et citations** : lorsque vous exécutez le script et posez des questions, l'algorithme récupère les documents les plus pertinents, produit une réponse concise et indique les sources utilisées.
3. **Évaluation et auto‑évolution** : chaque réponse est évaluée selon un critère simple (présence d'au moins deux sources distinctes). Le système ajuste ensuite un paramètre interne (seuil de similarité) afin d'améliorer ses performances au fil du temps. Les interactions sont consignées dans `logs.json`.
4. **Tableau de bord** : la page `dashboard/dashboard.html` permet de visualiser l'historique des requêtes et l'évolution de la qualité des réponses. Elle utilise Tailwind CSS et Chart.js via des CDN pour l'apparence et les graphiques. Pour visualiser cette page, lancez un serveur HTTP local (voir ci‑dessous).

## Installation

Installez les dépendances minimales pour le serveur web (Windows PowerShell) :

1) Activez votre environnement virtuel si vous en avez un, par exemple :

  .\.venv\Scripts\Activate.ps1

2) Installez les paquets requis :

  pip install -r requirements.txt

## Utilisation

### 1. Exécuter le script

```bash
python main.py
```

Le script vous invitera à saisir des questions. Entrez une question pertinente (par exemple : « Qu'est‑ce qu'un agent auto‑évolutif ? ») puis appuyez sur Entrée. Le système affichera la réponse, les sources citées et mettra à jour `logs.json`.

Pour terminer la session, saisissez `quit`.

### 2. Démarrer le serveur web + dashboard

Lancez le serveur Flask qui expose des endpoints de contrôle (start/stop/ask/evolve) et sert le dashboard :

  python server.py

Puis ouvrez votre navigateur sur : http://127.0.0.1:8000/

Depuis la page, vous pouvez démarrer/arrêter le worker, poser des questions et lancer une petite évolution de la stratégie.

## Structure des fichiers

- `main.py` : script principal pour interroger l'IA et enregistrer les logs.
- `dummy_data.json` : documents factices utilisés pour l'indexation.
- `logs.json` : fichier JSON contenant l'historique des interactions et des performances (créé/complété automatiquement).
- `dashboard/dashboard.html` : page web statique affichant les logs et graphiques.
 - `server.py` : serveur Flask exposant les API et servant le dashboard.
 - `strategy.py` : stratégie d'ajustement de paramètres, modifiable par l'evolver.
- `core/crawler.py` : récupération simple d'une page web et intégration au dataset.

Organisation conseillée pour évoluer :

- `core/` : modules cœur (indexation, retrieval, LLM, crawler, évaluation…)
- `api/` : endpoints web (Flask/FastAPI) et schémas
- `ui/` : frontend (dashboard)
- `data/` : jeux de données, snapshots, caches

## Notes importantes

- Ce prototype n'utilise pas de réseau pour collecter des données en direct. Les fonctions de crawling et d'auto‑modification du code sont simplifiées. Pour un système complet, vous devrez :
  - Implémenter un crawler respectueux de `robots.txt` pour collecter de nouveaux documents.
  - Remplacer l'algorithme de similarité par un moteur d'embeddings (FAISS/Chroma) et un modèle LLM pour générer des réponses de haute qualité.
  - Mettre en œuvre des évaluations plus sophistiquées (exactitude, hallucination, diversité) et un moteur d'auto‑évolution inspiré des cadres EvoAgentX et Darwin Gödel Machine.
- Le tableau de bord est servi par Flask (`server.py`) et communique via des endpoints REST.
- Le crawler fourni est minimal (pas de robots.txt, pas de rendu JS). Pour un usage réel, utilisez des bibliothèques dédiées (Ex: scrapy, playwright) et respectez les politiques des sites.

## Rebuild Docker complet

Des scripts utilitaires ont été ajoutés pour reconstruire entièrement la stack (backend + frontend + services) :

Linux / macOS :
```bash
./scripts/rebuild_all.sh
```

Windows PowerShell :
```powershell
./scripts/rebuild_all.ps1
```

Ce que fait le script :
1. `docker compose down --remove-orphans`
2. `docker compose build --no-cache`
3. `docker compose up -d`
4. Attente active jusqu'à ce que `http://localhost:8000/health` réponde OK.

Échec si le backend n'est pas sain après ~60s.