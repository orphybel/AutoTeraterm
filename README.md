# AutoTeraTerm v2.0

Automatisation de sessions SSH TeraTerm sur Windows.  
Ouvre plusieurs fenêtres TeraTerm en parallèle (ou en séquence) et exécute des commandes prédéfinies sur chaque cible.

---

## Prérequis

- Windows 10 / 11
- Python 3.9+
- [TeraTerm](https://github.com/TeraTermProject/teraterm/releases) installé

Aucune dépendance externe — uniquement la bibliothèque standard Python.

---

## Démarrage rapide

```bat
REM 1. Générer les fichiers de configuration par défaut
python auto_teraterm.py --init

REM 2. Éditer config.ini (chemin TeraTerm, options) et jobs.ini (vos sessions)

REM 3. Lancer
python auto_teraterm.py
```

---

## Structure des fichiers

```
AutoTeraterm/
├── auto_teraterm.py   ← script principal
├── config.ini         ← configuration globale
└── jobs.ini           ← définition des sessions SSH
```

---

## config.ini — Configuration globale

| Section | Clé | Défaut | Description |
|---|---|---|---|
| `[teraterm]` | `path` | *(vide)* | Chemin vers `ttermpro.exe`. Vide = détection automatique |
| `[session]` | `port` | `22` | Port SSH par défaut |
| `[session]` | `ssh_version` | `2` | Version SSH (`1` ou `2`) |
| `[session]` | `connect_pause` | `3` | Délai (s) après connexion |
| `[session]` | `pause` | `2` | Délai (s) entre chaque commande |
| `[session]` | `no_security_warning` | `true` | Supprimer l'alerte SSH au premier accès |
| `[session]` | `set_window_title` | `true` | Afficher le nom de session dans la barre de titre |
| `[execution]` | `parallel` | `true` | `true` = toutes les sessions simultanées, `false` = séquentiel |
| `[execution]` | `launch_delay` | `0.5` | Délai (s) entre chaque lancement en mode parallèle |
| `[execution]` | `keep_macros` | `false` | Conserver les fichiers `.ttl` temporaires |
| `[execution]` | `macro_dir` | *(vide)* | Dossier pour les `.ttl` (vide = temp système) |

---

## jobs.ini — Définition des sessions

Chaque section `[Nom]` représente une session SSH.

```ini
[Mon-Routeur]
ip    = 192.168.1.1
user  = admin
pass  = motdepasse
port  = 22        # optionnel
pause = 2         # optionnel
commands =
    show version
    show ip interface brief
```

**Champs obligatoires :** `ip`, `user`, `pass`, `commands`  
**Champs optionnels :** `port`, `pause` (héritent de `config.ini`)

---

## Options en ligne de commande

```
python auto_teraterm.py [OPTIONS]

  -j, --jobs FICHIER        Fichier de sessions (défaut : jobs.ini)
  -c, --config FICHIER      Fichier de config   (défaut : config.ini)
  -n, --dry-run             Affiche les macros sans lancer TeraTerm
  -v, --verbose             Journalisation détaillée
  -s, --sequential          Mode séquentiel (attend la fermeture de chaque session)
      --teraterm CHEMIN     Chemin vers ttermpro.exe (prioritaire sur config.ini)
      --init                Crée config.ini et jobs.ini avec des exemples
      --version             Affiche la version
```

### Exemples

```bat
REM Sessions depuis un autre fichier
python auto_teraterm.py --jobs routeurs_datacenter.ini

REM Tester sans rien lancer
python auto_teraterm.py --dry-run --verbose

REM Spécifier TeraTerm manuellement
python auto_teraterm.py --teraterm "C:\outils\teraterm\ttermpro.exe"

REM Mode séquentiel : une session à la fois
python auto_teraterm.py --sequential

REM Config et sessions personnalisées
python auto_teraterm.py -c prod.ini -j prod_sessions.ini
```

---

## Détection automatique de TeraTerm

Si `path` est vide dans `config.ini`, le script cherche TeraTerm dans :

1. Le registre Windows (`HKLM\SOFTWARE\TeraTermProject\Tera Term`)
2. Les chemins courants :
   - `C:\Program Files\teraterm\ttermpro.exe`
   - `C:\Program Files (x86)\teraterm\ttermpro.exe`
   - `C:\tools\teraterm\ttermpro.exe`
   - `C:\teraterm\ttermpro.exe`

---

## Modes d'exécution

| Mode | Comportement |
|---|---|
| **Parallèle** (défaut) | Toutes les fenêtres TeraTerm s'ouvrent simultanément avec un délai de `launch_delay` secondes entre chaque lancement |
| **Séquentiel** (`--sequential`) | Chaque session attend que la fenêtre TeraTerm précédente soit **fermée** avant de s'ouvrir |

---

## Note de sécurité

Les mots de passe sont stockés en clair dans `jobs.ini`.  
Restreignez les permissions du fichier (`icacls jobs.ini /inheritance:r /grant:r "%USERNAME%":F`).
