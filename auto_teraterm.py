# Auto Tera Term launcher
# Voir la conversation pour le format jobs.txt

import os
import subprocess
import tempfile
import sys
from ipaddress import ip_address

DEFAULT_JOBS_FILE = "jobs.txt"

def parse_jobs_file(path):
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    sessions=[]
    tterm_path=None
    with open(path,encoding="utf-8") as f:
        lines=[l.rstrip("\n") for l in f]
    current={}
    cmds=[]
    in_commands=False
    def flush():
        nonlocal current,cmds
        if current and all(k in current for k in ("ip","user","pass")) and cmds:
            sessions.append({"ip":current["ip"],"user":current["user"],"pass":current["pass"],"commands":cmds.copy()})
        current={}
        cmds=[]
    for raw in lines:
        line=raw.strip()
        if not line:
            if in_commands:
                in_commands=False
                flush()
            continue
        if line.startswith("#"):
            continue
        if line.lower().startswith("teraterm="):
            p=line.split("=",1)[1].strip().strip('"')
            tterm_path=p
            continue
        if line.lower().startswith("ip="):
            if current and not in_commands:
                flush()
            current["ip"]=line.split("=",1)[1].strip(); continue
        if line.lower().startswith("user="):
            current["user"]=line.split("=",1)[1].strip(); continue
        if line.lower().startswith("pass="):
            current["pass"]=line.split("=",1)[1].strip(); continue
        if line.lower().startswith("commands:"):
            in_commands=True
            cmds=[]
            continue
        if in_commands:
            cmds.append(line)
    if current:
        flush()
    return tterm_path,sessions

def build_macro(s,pause=2):
    m=[f"connect '{s['ip']}:22 /ssh /2 /auth=password /user={s['user']} /passwd={s['pass']} /nosecuritywarning'","pause 2"]
    for c in s["commands"]:
        m.append(f"sendln '{c.replace(\"'\",\"''\")}'")
        m.append(f"pause {pause}")
    return "\n".join(m)

def main():
    jobs=sys.argv[1] if len(sys.argv)>1 else DEFAULT_JOBS_FILE
    tterm,sessions=parse_jobs_file(jobs)
    for s in sessions:
        txt=build_macro(s)
        with tempfile.NamedTemporaryFile("w",delete=False,suffix=".ttl",encoding="utf-8") as f:
            f.write(txt)
            macro=f.name
        subprocess.Popen([tterm,"/M="+macro])

if __name__=="__main__":
    main()
