# Auto Tera Term launcher
# Format jobs.txt : teraterm= et section commands: uniquement (ip/user/pass dans la fenetre)

import os
import subprocess
import tempfile
import sys
import tkinter as tk
from tkinter import ttk, messagebox
from ipaddress import ip_address

DEFAULT_JOBS_FILE = "jobs.txt"


def parse_jobs_file(path):
    """Lit le fichier jobs : chemin TeraTerm + liste de commandes uniquement."""
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    tterm_path = None
    cmds = []
    in_commands = False
    with open(path, encoding="utf-8") as f:
        lines = [l.rstrip("\n") for l in f]
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("teraterm="):
            tterm_path = line.split("=", 1)[1].strip().strip('"')
            continue
        if line.lower().startswith("commands:"):
            in_commands = True
            cmds = []
            continue
        if in_commands:
            cmds.append(line)
    return tterm_path, cmds


def build_macro(ip, user, password, commands, pause=2):
    m = [
        f"connect '{ip}:22 /ssh /2 /auth=password /user={user} /passwd={password} /nosecuritywarning'",
        "pause 2",
    ]
    for c in commands:
        m.append(f"sendln '{c.replace(chr(39), chr(39)*2)}'")
        m.append(f"pause {pause}")
    return "\n".join(m)


def launch_sessions(tterm_path, base_ip, user, password, commands, count):
    base = ip_address(base_ip)
    for i in range(count):
        ip = str(base + i)
        txt = build_macro(ip, user, password, commands)
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".ttl", encoding="utf-8") as f:
            f.write(txt)
            macro = f.name
        subprocess.Popen([tterm_path, "/M=" + macro])


class DeviceConfigWindow:
    def __init__(self, root, jobs_file):
        self.root = root
        self.jobs_file = jobs_file
        self.root.title("AutoTeraTerm")
        self.root.resizable(False, False)

        frame = ttk.Frame(root, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")

        ttk.Label(frame, text="Nbre d'appareils :").grid(row=0, column=0, sticky="w", pady=5)
        self.count_var = tk.StringVar(value="1")
        ttk.Entry(frame, textvariable=self.count_var, width=22).grid(row=0, column=1, pady=5, padx=(10, 0))

        ttk.Label(frame, text="Adresse IP :").grid(row=1, column=0, sticky="w", pady=5)
        self.ip_var = tk.StringVar(value="192.168.1.1")
        ttk.Entry(frame, textvariable=self.ip_var, width=22).grid(row=1, column=1, pady=5, padx=(10, 0))

        ttk.Label(frame, text="Utilisateur :").grid(row=2, column=0, sticky="w", pady=5)
        self.user_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.user_var, width=22).grid(row=2, column=1, pady=5, padx=(10, 0))

        ttk.Label(frame, text="Mot de passe :").grid(row=3, column=0, sticky="w", pady=5)
        self.pass_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.pass_var, show="*", width=22).grid(row=3, column=1, pady=5, padx=(10, 0))

        ttk.Button(frame, text="Lancer", command=self.on_launch).grid(
            row=4, column=0, columnspan=2, pady=(14, 0)
        )

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

        try:
            tterm_path, commands = parse_jobs_file(self.jobs_file)
        except FileNotFoundError:
            messagebox.showerror("Erreur", f"Fichier introuvable : {self.jobs_file}")
            return

        if not tterm_path:
            messagebox.showerror(
                "Erreur",
                "Le chemin TeraTerm (teraterm=...) est absent du fichier jobs.",
            )
            return

        if not commands:
            messagebox.showerror("Erreur", "Aucune commande trouvée dans le fichier jobs.")
            return

        self.root.destroy()
        launch_sessions(tterm_path, ip_str, user, password, commands, count)


def main():
    jobs = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_JOBS_FILE
    root = tk.Tk()
    DeviceConfigWindow(root, jobs)
    root.mainloop()


if __name__ == "__main__":
    main()
