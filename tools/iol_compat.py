#!/usr/bin/python3
"""Replay a config file line by line on a live IOL node and record which commands IOS rejects.

usage: iol_compat.py CONFIG.cfg [--host clab-iolcompat-sw] [--json ../standards/iol_l2_compat.json]
Results are merged into the JSON keyed by the config file name, so later files add to it.
Run each file on a FRESH node (clab destroy/deploy): "crypto key zeroize rsa" etc. kill SSH for later runs.
"""
import argparse, json, os, re, time, datetime, paramiko

ERR = re.compile(r"^% (Invalid input|Incomplete command|Ambiguous command|Unrecognized command|.*not supported|.*Bad|.*Invalid)", re.M)
PROMPT = re.compile(r"(\S+?)(\((config[^)]*)\))?#\s*$")
CONFIRM = re.compile(r"\[(yes/no|confirm)\]:?\s*$|\[y/n\]:?\s*$|\? \[.*\]\s*$", re.I)

ap = argparse.ArgumentParser()
ap.add_argument("cfg"); ap.add_argument("--host", default="clab-iolcompat-sw")
ap.add_argument("--json", default=os.path.join(os.path.dirname(__file__), "../standards/iol_l2_compat.json"))
a = ap.parse_args()

c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(a.host, username="admin", password="admin", look_for_keys=False, allow_agent=False,
          disabled_algorithms={}, timeout=10)
sh = c.invoke_shell(width=500); sh.settimeout(0.3)

def send(cmd, wait=8.0):
    """Send one line, return output up to the next prompt. Answers y/n confirmations."""
    sh.send(cmd + "\n"); buf = ""; end = time.time() + wait
    while time.time() < end:
        try: buf += sh.recv(65535).decode(errors="replace")
        except Exception: pass
        tail = buf.rstrip("\n").split("\n")[-1] if buf else ""
        if PROMPT.search(tail) and cmd.strip() in buf: break
        if CONFIRM.search(tail): sh.send("yes\n" if "yes/no" in tail else "\n")
    return buf

send("terminal length 0"); send("terminal width 0")
version = send("show version")
ver = re.search(r"Version ([\w.()]+)", version); ver = ver.group(1) if ver else "?"
mode = (PROMPT.search(send("configure terminal").rstrip().split("\n")[-1]) or [None]*4)[3]

SECTIONS = [(r"^interface ", "interface"), (r"^router ospf", "ospf"), (r"^router bgp", "bgp"), (r"^router (\w+)", None),
            (r"^(ip|ipv6|mac) access-list|^access-list", "acl"), (r"^line ", "line"), (r"^(ip )?vrf |^vrf ", "vrf"),
            (r"^vlan ", "vlan"), (r"^route-map ", "route-map")]
def section(parent):  # category of the section a child command lives in; unknown parents fall back to their first word
    for rx, name in SECTIONS:
        m = re.match(rx, parent)
        if m: return name or m.group(1)
    return parent.split()[0]

count = {"ok": 0, "error": 0, "skipped": 0}; failing = []
comment, parent_failed, bad_parent, parent = [], False, None, None
for raw in open(a.cfg).read().splitlines():
    s = raw.strip()
    if not s or s == "!": comment = [] if s == "!" else comment; continue
    if s.startswith("!"): comment.append(s.lstrip("! ")); continue
    child = raw.startswith(" ") or s[0].isdigit()
    if not child: parent = s
    if child and parent_failed:
        count["skipped"] += 1                      # untested: its parent was rejected
    else:
        if not child:                              # top-level line: leave any sub-mode first
            for _ in range(4):                     # never exit from plain "config" (that would leave config mode)
                if mode in (None, "config"): break
                m = PROMPT.search(send("exit").rstrip().split("\n")[-1]); mode = m.group(3) if m else None
            parent_failed = False
        out = send(s)
        lines = [l for l in out.replace("\r", "").split("\n")[1:] if l.strip()]
        m = PROMPT.search(lines[-1]) if lines else None
        err = " | ".join(l.strip() for l in lines if l.startswith("%")) if ERR.search(out) else None
        mode = m.group(3) if m else mode
        count["error" if err else "ok"] += 1
        if err:
            failing.append({"command": s, "section": section(parent) if child else "global config",
                            **({"parent": parent} if child else {}), "error": err, "note": " ".join(comment) or None})
            if not child: parent_failed, bad_parent = True, s
    comment = []
send("end"); c.close()

try: db = json.load(open(a.json))
except FileNotFoundError: db = {"files": {}}
db["platform"] = "cisco_iol L2 (IOL-L2 XE)"; db["image_version"] = ver
db["files"][os.path.basename(a.cfg)] = {
    "tested_at": datetime.datetime.now().isoformat(timespec="seconds"), "summary": count, "failing": failing}
json.dump(db, open(a.json, "w"), indent=2)
print(f"IOS {ver}: {sum(count.values())} commands, {count['ok']} ok, {count['error']} rejected, {count['skipped']} skipped (parent rejected)")
for r in failing: print(f"  [{r['section']}] {r['command']}  -> {r['error']}")
