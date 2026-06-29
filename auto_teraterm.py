"""
AutoTeraTerm v2.0 — Automatisation de sessions SSH TeraTerm sur Windows
"""

from __future__ import annotations

import os
import sys
import time
import logging
import tempfile
import subprocess
import argparse
import configparser
from ipaddress import ip_address

try:
    import winreg
except ImportError:
    winreg = None  # type: ignore[assignment]

# ─── Version ───────────────────────────────────────────────────────────────────

VERSION = "2.0.0"
DEFAULT_CONFIG = "config.ini"
DEFAULT_JOBS = "jobs.ini"

# ─── TeraTerm auto-détection ───────────────────────────────────────────────────

_REGISTRY_KEYS = [
    (winreg.HKEY_LOCAL_MACHINE if winreg else None, r"SOFTWARE\TeraTermProject\Tera Term"),
    (winreg.HKEY_LOCAL_MACHINE if winreg else None, r"SOFTWARE\WOW6432Node\TeraTermProject\Tera Term"),
    (winreg.HKEY_CURRENT_USER  if winreg else None, r"SOFTWARE\TeraTermProject\Tera Term"),
]

_COMMON_PATHS = [
    r"C:\Program Files\teraterm\ttermpro.exe",
    r"C:\Program Files (x86)\teraterm\ttermpro.exe",
    r"C:\tools\teraterm\ttermpro.exe",
    r"C:\teraterm\ttermpro.exe",
]


def find_teraterm() -> str | None:
    """Cherche ttermpro.exe dans le registre Windows puis dans les chemins courants."""
    if winreg:
        for hive, sub in _REGISTRY_KEYS:
            if hive is None:
                continue
            try:
                with winreg.OpenKey(hive, sub) as key:
                    install_dir, _ = winreg.QueryValueEx(key, "InstallDir")
                    candidate = os.path.join(install_dir, "ttermpro.exe")
                    if os.path.isfile(candidate):
                        return candidate
            except OSError:
                pass
    for p in _COMMON_PATHS:
        if os.path.isfile(p):
            return p
    return None


# ─── Logging ───────────────────────────────────────────────────────────────────

def setup_logging(verbose: bool) -> logging.Logger:
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "[%(asctime)s] %(levelname)-8s %(message)s"
    logging.basicConfig(level=level, format=fmt, datefmt="%H:%M:%S",
                        handlers=[logging.StreamHandler(sys.stdout)])
    return logging.getLogger("autott")


# ─── Configuration globale ─────────────────────────────────────────────────────

_CONFIG_DEFAULTS: dict[str, dict[str, str]] = {
    "teraterm": {
        "path": "",
    },
    "session": {
        "port": "22",
        "ssh_version": "2",
        "connect_pause": "3",
        "pause": "2",
        "no_security_warning": "true",
        "set_window_title": "true",
    },
    "execution": {
        "parallel": "true",
        "launch_delay": "0.5",
        "keep_macros": "false",
        "macro_dir": "",
    },
}


def load_config(path: str) -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    cfg.read_dict(_CONFIG_DEFAULTS)
    if os.path.isfile(path):
        cfg.read(path, encoding="utf-8")
    return cfg


def generate_config(path: str) -> None:
    content = """\
# ================================================================
#  AutoTeraTerm — Configuration globale
# ================================================================

[teraterm]
# Chemin complet vers ttermpro.exe
# Laisser vide pour la détection automatique (registre + chemins courants)
path =

[session]
# Port SSH par défaut (peut être surchargé par session dans jobs.ini)
port = 22

# Version du protocole SSH : 1 ou 2
ssh_version = 2

# Pause en secondes après l'établissement de la connexion
connect_pause = 3

# Pause en secondes entre chaque commande envoyée
pause = 2

# Désactiver l'avertissement de sécurité SSH au premier accès
no_security_warning = true

# Afficher le nom de la session dans la barre de titre TeraTerm
set_window_title = true

[execution]
# true  → toutes les sessions s'ouvrent en parallèle
# false → chaque session attend la fermeture de la précédente
parallel = true

# Délai (secondes) entre chaque lancement en mode parallèle
launch_delay = 0.5

# true  → les fichiers .ttl temporaires sont conservés après exécution
# false → ils sont supprimés automatiquement (après un délai de sécurité)
keep_macros = false

# Répertoire de stockage des fichiers .ttl (vide = dossier temp système)
macro_dir =
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# ─── Parsing des sessions (jobs.ini) ──────────────────────────────────────────

def _validate_host(value: str) -> str:
    """Accepte une IP valide ou un hostname."""
    v = value.strip()
    try:
        ip_address(v)
        return v
    except ValueError:
        pass
    # Hostname : caractères autorisés
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._")
    if v and all(c in allowed for c in v):
        return v
    raise ValueError(f"IP / hostname invalide : '{value}'")


def parse_jobs(path: str, cfg: configparser.ConfigParser) -> list[dict]:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Fichier jobs introuvable : {path}")

    default_port  = cfg.getint("session", "port")
    default_pause = cfg.getfloat("session", "pause")

    jobs_cfg = configparser.ConfigParser()
    jobs_cfg.read(path, encoding="utf-8")

    if not jobs_cfg.sections():
        raise ValueError("Aucune session trouvée dans le fichier jobs.")

    sessions: list[dict] = []
    errors: list[str] = []

    for name in jobs_cfg.sections():
        s = jobs_cfg[name]
        missing = [k for k in ("ip", "user", "pass") if k not in s or not s[k].strip()]
        if missing:
            errors.append(f"[{name}] Champs manquants ou vides : {', '.join(missing)}")
            continue

        try:
            ip = _validate_host(s["ip"])
        except ValueError as e:
            errors.append(f"[{name}] {e}")
            continue

        commands = [l.strip() for l in s.get("commands", "").splitlines() if l.strip()]
        if not commands:
            errors.append(f"[{name}] Aucune commande définie (champ 'commands' manquant ou vide)")
            continue

        try:
            port  = int(s.get("port",  str(default_port)))
            pause = float(s.get("pause", str(default_pause)))
        except ValueError as e:
            errors.append(f"[{name}] Valeur numérique invalide : {e}")
            continue

        sessions.append({
            "name":     name,
            "ip":       ip,
            "user":     s["user"].strip(),
            "pass":     s["pass"].strip(),
            "port":     port,
            "pause":    pause,
            "commands": commands,
        })

    if errors:
        raise ValueError("Erreurs dans le fichier jobs :\n  " + "\n  ".join(errors))

    return sessions


def generate_jobs(path: str) -> None:
    content = """\
# ================================================================
#  AutoTeraTerm — Définition des sessions SSH
# ================================================================
# Chaque section [Nom de session] décrit une connexion SSH.
#
# Champs OBLIGATOIRES :
#   ip       = adresse IP ou hostname de la cible
#   user     = nom d'utilisateur SSH
#   pass     = mot de passe SSH
#   commands = liste de commandes (une par ligne, indentées)
#
# Champs OPTIONNELS (héritent de config.ini si omis) :
#   port  = port SSH (défaut : 22)
#   pause = délai entre commandes en secondes (défaut : 2)
#
# Les lignes commençant par # sont des commentaires.
# ================================================================

[Routeur-Core-1]
ip    = 192.168.1.1
user  = admin
pass  = changeme
commands =
    show version
    show ip interface brief
    show running-config

[Switch-Acces-2]
ip    = 192.168.1.2
user  = admin
pass  = changeme
port  = 22
pause = 3
commands =
    show version
    show vlan brief
    show interfaces status

[Serveur-Linux]
ip    = 10.0.0.10
user  = root
pass  = changeme
commands =
    uname -a
    df -h
    uptime
    who
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# ─── Construction de la macro TeraTerm (.ttl) ──────────────────────────────────

def build_macro(s: dict, cfg: configparser.ConfigParser) -> str:
    ssh_ver       = cfg.getint("session", "ssh_version")
    connect_pause = cfg.getfloat("session", "connect_pause")
    no_warn       = cfg.getboolean("session", "no_security_warning")
    set_title     = cfg.getboolean("session", "set_window_title")

    def esc(text: str) -> str:
        """Échappe les apostrophes pour les littéraux TeraTerm."""
        return text.replace("'", "''")

    flags = f"/ssh /{ssh_ver} /auth=password /user={esc(s['user'])} /passwd={esc(s['pass'])}"
    if no_warn:
        flags += " /nosecuritywarning"

    lines = [
        f"; AutoTeraTerm v{VERSION} — Session : {s['name']}",
        f"connect '{s['ip']}:{s['port']} {flags}'",
        f"pause {connect_pause:.1f}",
    ]

    if set_title:
        lines.append(f"titleset '{esc(s['name'])} — {s['ip']}'")

    lines.append("")  # ligne vide pour lisibilité

    for cmd in s["commands"]:
        lines.append(f"sendln '{esc(cmd)}'")
        lines.append(f"pause {s['pause']:.1f}")

    return "\n".join(lines) + "\n"


# ─── Lancement des sessions ────────────────────────────────────────────────────

def _macro_dir(cfg: configparser.ConfigParser) -> str | None:
    d = cfg.get("execution", "macro_dir").strip()
    if d:
        os.makedirs(d, exist_ok=True)
        return d
    return None


def launch_session(
    s: dict,
    tterm: str,
    cfg: configparser.ConfigParser,
    log: logging.Logger,
    dry_run: bool,
) -> str | None:
    """Écrit la macro et lance TeraTerm. Retourne le chemin du fichier .ttl."""
    macro_text = build_macro(s, cfg)

    fd_kwargs: dict = {"mode": "w", "suffix": ".ttl", "encoding": "utf-8", "delete": False}
    d = _macro_dir(cfg)
    if d:
        fd_kwargs["dir"] = d

    with tempfile.NamedTemporaryFile(**fd_kwargs) as f:
        f.write(macro_text)
        macro_path = f.name

    log.debug(f"[{s['name']}] Macro : {macro_path}")

    if dry_run:
        log.info(f"[DRY-RUN] [{s['name']}] {s['ip']}:{s['port']} — macro :\n{macro_text}")
        os.unlink(macro_path)
        return None

    log.info(
        f"[{s['name']}] {s['ip']}:{s['port']}  "
        f"user={s['user']}  {len(s['commands'])} commande(s)"
    )
    subprocess.Popen([tterm, f"/M={macro_path}"])
    return macro_path


def run_sessions(
    sessions: list[dict],
    tterm: str,
    cfg: configparser.ConfigParser,
    log: logging.Logger,
    dry_run: bool,
) -> None:
    parallel     = cfg.getboolean("execution", "parallel")
    launch_delay = cfg.getfloat("execution", "launch_delay")
    keep_macros  = cfg.getboolean("execution", "keep_macros")

    mode_label = "parallèle" if parallel else "séquentiel"
    log.info(f"{len(sessions)} session(s) — mode {mode_label}")

    temp_files: list[str] = []

    for i, s in enumerate(sessions):
        if parallel:
            macro_path = launch_session(s, tterm, cfg, log, dry_run)
            if macro_path:
                temp_files.append(macro_path)
            if i < len(sessions) - 1:
                time.sleep(launch_delay)
        else:
            # Mode séquentiel : attendre la fermeture de TeraTerm avant de continuer
            macro_text = build_macro(s, cfg)
            fd_kwargs: dict = {"mode": "w", "suffix": ".ttl", "encoding": "utf-8", "delete": False}
            d = _macro_dir(cfg)
            if d:
                fd_kwargs["dir"] = d
            with tempfile.NamedTemporaryFile(**fd_kwargs) as f:
                f.write(macro_text)
                macro_path = f.name

            if dry_run:
                log.info(f"[DRY-RUN] [{s['name']}] {s['ip']}:{s['port']} — macro :\n{macro_text}")
                os.unlink(macro_path)
            else:
                log.info(
                    f"[{s['name']}] {s['ip']}:{s['port']}  "
                    f"user={s['user']}  {len(s['commands'])} commande(s)"
                )
                proc = subprocess.Popen([tterm, f"/M={macro_path}"])
                log.debug(f"[{s['name']}] En attente de la fermeture de TeraTerm...")
                proc.wait()
                log.debug(f"[{s['name']}] Session terminée.")
                if not keep_macros:
                    try:
                        os.unlink(macro_path)
                    except OSError:
                        pass

    # Nettoyage des macros en mode parallèle
    if temp_files and not keep_macros and not dry_run:
        log.debug("Attente avant suppression des fichiers macro...")
        time.sleep(5)
        for p in temp_files:
            try:
                os.unlink(p)
                log.debug(f"Macro supprimée : {p}")
            except OSError:
                pass


# ─── CLI ───────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="auto_teraterm",
        description=f"AutoTeraTerm v{VERSION} — Automatisation de sessions SSH TeraTerm",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  auto_teraterm.py
      → Lance jobs.ini avec config.ini

  auto_teraterm.py --jobs mes_routeurs.ini
      → Utilise un fichier de sessions personnalisé

  auto_teraterm.py --config mon_config.ini --jobs mes_sessions.ini
      → Configuration et sessions personnalisées

  auto_teraterm.py --dry-run --verbose
      → Affiche les macros générées sans rien lancer

  auto_teraterm.py --teraterm "C:\\tools\\ttermpro.exe"
      → Spécifie manuellement le chemin TeraTerm

  auto_teraterm.py --sequential
      → Ouvre les sessions l'une après l'autre (attend la fermeture)

  auto_teraterm.py --init
      → Crée config.ini et jobs.ini avec des valeurs par défaut
        """,
    )

    p.add_argument(
        "-j", "--jobs",
        default=DEFAULT_JOBS, metavar="FICHIER",
        help=f"Fichier de sessions INI (défaut : {DEFAULT_JOBS})",
    )
    p.add_argument(
        "-c", "--config",
        default=DEFAULT_CONFIG, metavar="FICHIER",
        help=f"Fichier de configuration INI (défaut : {DEFAULT_CONFIG})",
    )
    p.add_argument(
        "-n", "--dry-run",
        action="store_true",
        help="Génère et affiche les macros sans lancer TeraTerm",
    )
    p.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Journalisation détaillée (debug)",
    )
    p.add_argument(
        "-s", "--sequential",
        action="store_true",
        help="Mode séquentiel : attend la fermeture de chaque session avant la suivante",
    )
    p.add_argument(
        "--teraterm", metavar="CHEMIN",
        help="Chemin vers ttermpro.exe (prioritaire sur config.ini)",
    )
    p.add_argument(
        "--init",
        action="store_true",
        help=f"Crée {DEFAULT_CONFIG} et {DEFAULT_JOBS} avec des valeurs d'exemple",
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {VERSION}",
    )
    return p


# ─── Point d'entrée ────────────────────────────────────────────────────────────

def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    log = setup_logging(args.verbose)

    log.info(f"AutoTeraTerm v{VERSION}")

    # ── Mode initialisation ──────────────────────────────────────────────────
    if args.init:
        created = False
        for path, fn in [(DEFAULT_CONFIG, generate_config), (DEFAULT_JOBS, generate_jobs)]:
            if os.path.exists(path):
                log.warning(f"Fichier déjà existant, ignoré : {path}")
            else:
                fn(path)
                log.info(f"Fichier créé : {path}")
                created = True
        if not created:
            log.info("Aucun fichier à créer (ils existent déjà).")
        return 0

    # ── Chargement de la configuration ──────────────────────────────────────
    if not os.path.isfile(args.config):
        log.warning(f"config.ini introuvable ({args.config}), utilisation des valeurs par défaut.")
    cfg = load_config(args.config)

    if args.sequential:
        cfg.set("execution", "parallel", "false")

    # ── Résolution du chemin TeraTerm ────────────────────────────────────────
    tterm = (args.teraterm or cfg.get("teraterm", "path")).strip()

    if not args.dry_run:
        if not tterm:
            log.debug("Recherche automatique de TeraTerm...")
            tterm = find_teraterm() or ""

        if not tterm:
            log.error(
                "TeraTerm introuvable. Solutions :\n"
                "  1. Spécifiez le chemin dans config.ini → [teraterm] path = ...\n"
                "  2. Utilisez l'option --teraterm \"C:\\...\\ttermpro.exe\"\n"
                "  3. Installez TeraTerm dans un répertoire standard"
            )
            return 1

        if not os.path.isfile(tterm):
            log.error(f"Exécutable TeraTerm introuvable : {tterm}")
            return 1

        log.info(f"TeraTerm : {tterm}")

    # ── Chargement des sessions ──────────────────────────────────────────────
    try:
        sessions = parse_jobs(args.jobs, cfg)
    except FileNotFoundError as e:
        log.error(str(e))
        log.info(f"Conseil : lancez  python auto_teraterm.py --init  pour créer {DEFAULT_JOBS}")
        return 1
    except ValueError as e:
        log.error(str(e))
        return 1

    log.info(f"{len(sessions)} session(s) chargée(s) depuis {args.jobs}")

    # ── Lancement ────────────────────────────────────────────────────────────
    run_sessions(sessions, tterm, cfg, log, args.dry_run)

    if args.dry_run:
        log.info("[DRY-RUN] Terminé — aucune session réellement lancée.")
    else:
        log.info("Toutes les sessions ont été lancées.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
