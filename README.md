# Projet Flask

Application web de gestion de commandes avec intégration d'API de paiement externe.

## 💻 Technologies
- **Backend** : Python 3.11 + Flask
- **ORM** : Peewee
- **Base de données** : SQLite
- **Tests** : Pytest
- **Services externes** :
  - API Produits : `http://dimensweb.uqac.ca/~jgnault/shops/products/`
  - API Paiement : `http://dimensweb.uqac.ca/~ignault/shops/pay/`


## Installation

Pour installer les dépendances nécessaires, utilisez la commande suivante :

```bash
pip install peewee flask pytest pytest-flask
```

## Configuration
1. Accéder au répertoire du projet

```bash
cd chemin/vers/votre/projet
```

2. Paramètres pour Windows

Définissez les variables d'environnement :

```powershell
$env:FLASK_APP = "app.py"
$env:FLASK_DEBUG = "1"
```

## Initialisation de la base de données

```bash
python -m flask init-db
```

## Lancement de l'application
```bash
python -m flask run
```

L'application sera accessible à l'adresse : http://localhost:5000

## Exécution des tests

Pour vérifier le bon fonctionnement du projet, lancez les tests avec :

```bash
pytest
```