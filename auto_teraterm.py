# Auto Tera Term launcher
# config.ini : chemin TeraTerm, pauses, valeurs par defaut (a editer a la main)
# Format jobs.txt : section commands: uniquement (ip/user/pass/teraterm dans config.ini / la fenetre)

import os
import subprocess
import tempfile
import sys
import configparser
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from ipaddress import ip_address

SSH_PORT = 22

DEFAULT_CONFIG = {
    "TeraTerm": {
        "chemin": r"C:\Program Files (x86)\teraterm\ttermpro.exe",
    },
    "Connexion": {
        "pause_connexion": "2",
        "pause_commande": "2",
    },
    "Defaut": {
        "nbre_appareils": "1",
        "adresse_ip": "10.15.150.186",
        "utilisateur": "admin",
    },
}


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_FILE = os.path.join(app_dir(), "config.ini")


def load_config():
    """Lit config.ini et le cree avec des valeurs par defaut si absent ou incomplet."""
    cfg = configparser.ConfigParser()
    if os.path.isfile(CONFIG_FILE):
        cfg.read(CONFIG_FILE, encoding="utf-8")
    changed = not os.path.isfile(CONFIG_FILE)
    for section, values in DEFAULT_CONFIG.items():
        if not cfg.has_section(section):
            cfg.add_section(section)
            changed = True
        for key, val in values.items():
            if not cfg.has_option(section, key):
                cfg.set(section, key, val)
                changed = True
    if changed:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            cfg.write(f)
    return cfg


def parse_jobs_file(path):
    """Lit le fichier jobs : liste de commandes uniquement."""
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    cmds = []
    in_commands = False
    with open(path, encoding="utf-8") as f:
        lines = [l.rstrip("\n") for l in f]
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("commands:"):
            in_commands = True
            cmds = []
            continue
        if in_commands:
            cmds.append(line)
    return cmds


def build_macro(ip, user, password, commands, pause_connexion=2, pause_commande=2):
    m = [
        f"connect '{ip}:{SSH_PORT} /ssh /2 /auth=password /user={user} /passwd={password} /nosecuritywarning'",
        f"pause {pause_connexion}",
    ]
    for c in commands:
        m.append(f"sendln '{c.replace(chr(39), chr(39)*2)}'")
        m.append(f"pause {pause_commande}")
    return "\n".join(m)


def launch_sessions(tterm_path, base_ip, user, password, commands, count, pause_connexion=2, pause_commande=2):
    base = ip_address(base_ip)
    for i in range(count):
        ip = str(base + i)
        txt = build_macro(ip, user, password, commands, pause_connexion, pause_commande)
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".ttl", encoding="utf-8") as f:
            f.write(txt)
            macro = f.name
        subprocess.Popen([tterm_path, "/M=" + macro])


class DeviceConfigWindow:
    def __init__(self, root, cfg, jobs_file=""):
        self.root = root
        self.cfg = cfg
        self.root.title("AutoTeraTerm")
        self.root.resizable(False, False)

        frame = ttk.Frame(root, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")

        ttk.Label(frame, text="Fichier jobs :").grid(row=0, column=0, sticky="w", pady=5)
        self.jobs_var = tk.StringVar(value=jobs_file)
        ttk.Entry(frame, textvariable=self.jobs_var, width=28).grid(row=0, column=1, pady=5, padx=(10, 0))
        ttk.Button(frame, text="...", width=3, command=self.browse_jobs).grid(row=0, column=2, padx=(4, 0))

        ttk.Separator(frame, orient="horizontal").grid(row=1, column=0, columnspan=3, sticky="ew", pady=8)

        ttk.Label(frame, text="Nbre d'appareils :").grid(row=2, column=0, sticky="w", pady=5)
        self.count_var = tk.StringVar(value=cfg.get("Defaut", "nbre_appareils"))
        ttk.Entry(frame, textvariable=self.count_var, width=22).grid(row=2, column=1, pady=5, padx=(10, 0))

        ttk.Label(frame, text="Adresse IP :").grid(row=3, column=0, sticky="w", pady=5)
        self.ip_var = tk.StringVar(value=cfg.get("Defaut", "adresse_ip"))
        ttk.Entry(frame, textvariable=self.ip_var, width=22).grid(row=3, column=1, pady=5, padx=(10, 0))

        ttk.Label(frame, text="Utilisateur :").grid(row=4, column=0, sticky="w", pady=5)
        self.user_var = tk.StringVar(value=cfg.get("Defaut", "utilisateur"))
        ttk.Entry(frame, textvariable=self.user_var, width=22).grid(row=4, column=1, pady=5, padx=(10, 0))

        ttk.Label(frame, text="Mot de passe :").grid(row=5, column=0, sticky="w", pady=5)
        self.pass_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.pass_var, show="*", width=22).grid(row=5, column=1, pady=5, padx=(10, 0))

        ttk.Button(frame, text="Lancer", command=self.on_launch).grid(
            row=6, column=0, columnspan=3, pady=(14, 0)
        )

    def browse_jobs(self):
        path = filedialog.askopenfilename(
            title="Sélectionner le fichier jobs",
            filetypes=[("Fichiers texte", "*.txt"), ("Tous les fichiers", "*.*")],
        )
        if path:
            self.jobs_var.set(path)

    def on_launch(self):
        try:
            count = int(self.count_var.get())
            if count < 1:
                raise ValueError
        except ValueError:
            messagebox.showerror("Erreur", "Le nombre d'appareils doit être un entier positif.")
            return

        ip_str = self.ip_var.get().strip()
        try:
            ip_address(ip_str)
        except ValueError:
            messagebox.showerror("Erreur", f"Adresse IP invalide : {ip_str}")
            return

        user = self.user_var.get().strip()
        if not user:
            messagebox.showerror("Erreur", "Le champ utilisateur est obligatoire.")
            return

        password = self.pass_var.get()

        jobs_path = self.jobs_var.get().strip()
        if not jobs_path:
            messagebox.showerror("Erreur", "Veuillez sélectionner un fichier jobs.")
            return

        try:
            commands = parse_jobs_file(jobs_path)
        except FileNotFoundError:
            messagebox.showerror("Erreur", f"Fichier introuvable : {jobs_path}")
            return

        if not commands:
            messagebox.showerror("Erreur", "Aucune commande trouvée dans le fichier jobs.")
            return

        tterm_path = self.cfg.get("TeraTerm", "chemin")
        if not tterm_path or not os.path.isfile(tterm_path):
            messagebox.showerror(
                "Erreur",
                f"Chemin TeraTerm introuvable : {tterm_path}\n"
                f"Corrigez-le dans {CONFIG_FILE}",
            )
            return

        pause_connexion = self.cfg.getfloat("Connexion", "pause_connexion")
        pause_commande = self.cfg.getfloat("Connexion", "pause_commande")

        self.root.destroy()
        launch_sessions(
            tterm_path, ip_str, user, password, commands, count,
            pause_connexion, pause_commande,
        )


def main():
    jobs = sys.argv[1] if len(sys.argv) > 1 else ""
    cfg = load_config()
    root = tk.Tk()
    DeviceConfigWindow(root, cfg, jobs)
    root.mainloop()


if __name__ == "__main__":
    main()
