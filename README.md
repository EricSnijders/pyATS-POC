# pyATS PoC — getting started

Goal: a small set of **topology-independent, read-only health checks** that run unchanged on any Cisco
environment (EVE-NG lab, physical lab, containerlab) by swapping only the testbed file.
Standards live in YAML (editable without coding); tests live in Python (few maintainers).

## Layout

```
standards/standards.yaml   what "good" looks like (versions, OSPF state, interface ignores)   <- many people
tests/health_checks.py     aetest checks, loop over every device in the testbed              <- few people
jobs/health_job.py         runs the checks (pyats run job)
testbeds/                  one per environment: device inventory + how to reach it
  clab-pyats-lab.yaml        -> symlink to ../../labs/pyats-lab/testbed.yaml   (working)
  eve-ng.yaml.example        template, UNTESTED
  physical-lab.yaml.example  template, UNTESTED
playbooks/                 empty; Ansible later (Ansible changes things, pyATS verifies them)
```

Related: the lab itself is in [../labs/pyats-lab/](../labs/pyats-lab/) (its README has the topology).

## Quick start (clab lab)

```bash
cd /root/containerlabs/labs/pyats-lab
clab deploy -t pyats-lab.clab.yaml          # wait ~2 min: vIOS needs it before SSH works
cd /root/containerlabs/pyats-poc
pyats run job jobs/health_job.py --testbed-file testbeds/clab-pyats-lab.yaml
```
Expected: connect x5 passed; OSPF passed on r1/r2/vr1 and *skipped* on the switches (no OSPF);
interfaces and versions passed. Clean up with `clab destroy -t pyats-lab.clab.yaml --cleanup`.

Use the **`pyats` CLI / `/usr/bin/python3`** — pyATS is installed in the system Python, not in `/root/.venv`.

## Everyday commands

```bash
T=testbeds/clab-pyats-lab.yaml
pyats parse "show version" --testbed-file $T                 # one command, all devices
pyats parse "show version" --testbed-file $T --devices r1 vr1   # space separated, NOT commas
pyats learn ospf --testbed-file $T --output snap1            # feature snapshot (normalised across OS)
#   ...make a change...
pyats learn ospf --testbed-file $T --output snap2
genie diff snap1 snap2                                       # what changed
pyats run job jobs/health_job.py --testbed-file $T           # the health checks
```
Read results: the per-device **summary box** at the end of `parse`; for jobs the log viewer
(`pyats logs view`, untested here). Filter noise: `... 2>&1 | grep -E "Summary for|Parsed|Could not|Failed"`.

## How to extend

- **Change a rule** (allowed versions, ignored interfaces, OSPF state): edit `standards/standards.yaml`. No code.
- **Add a check:** add a `Testcase` in `tests/health_checks.py`, copy an existing one. Pattern: loop over
  `reachable`, one `steps.start(dev.name)` per device, `step.skipped()` when the feature doesn't apply,
  `step.failed()` when the property is violated. Assert *properties* ("all neighbours FULL"), never
  topology-specific values ("r1 has neighbour 10.0.12.2") — that's what keeps it portable.
- **New environment:** copy an `.example` testbed into `testbeds/`, fill in devices. Tests don't change.
- A check that can't fail proves nothing: break the standard on purpose once (e.g. set `ios: ["15.6"]`) and
  confirm the job fails the right devices. Done for the version check; do it for any new one.

## Things learned (save yourself the time)

- **Genie parser coverage differs per OS.** `show ip ospf neighbor` has an `iosxe` parser but none for `ios`
  (only `... detail`). That's why `OspfNeighbors` tries both commands. Raw `device.execute()` always works.
  Try `os: iosxe` on classic-IOS boxes as a shortcut (ios parsers mostly subclass the iosxe ones) — untested here.
- **`pyats learn <feature>`** picks per-OS commands for you and returns one shape for IOS and XE; prefer it
  for snapshots/diffs. Use `parse` for ad-hoc commands or features without an Ops model.
- **`show parser dump` does not exist** on IOL, IOL-L2 or vIOS, so there is no exact command list from the
  devices. To find unsupported commands: push your standard config at the twin and log the `% Invalid input` lines.
  Keep a gap ledger per platform (rejected / accepted-but-no-effect) next to the standards.
- Virtual-platform lab quirks (also in the lab README):
  IOL configs must be named `*.partial.cfg`; this vIOS build applies *only* your config (mgmt, user, SSH keys,
  and `no switchport` on vIOS-L2 Gi0/0); `cisco_iol:l2-17.18.02` crashes on start; redeploy the whole lab,
  don't restart single nodes.
- **Credentials:** never put real passwords in a testbed. `"%ENV{USER}"` / `"%ENV{VAR}"` read the environment,
  `"%ASK{prompt}"` prompts at run time. Rotating TACACS passwords are handled by supplying the *current*
  one at run time (vault -> env var). pyATS does not rotate anything. Syntax is documented but only
  partly tried here.

## Status

| Verified in the clab lab | Not verified |
|---|---|
| 3 checks pass on IOS-XE + classic IOS + both switch types; version check fails correctly when the standard is broken | EVE-NG and physical-lab testbeds (templates only), jump host/proxy |
| OSPF FULL, cross-OS ping, VLAN 10 over mixed L2 trunk | `%ASK`/`%ENV` credentials, `pyats logs view`, Blitz/Robot, Ansible |

## Roadmap (when the PoC lands)

1. Run it on the EVE-NG lab: only a new testbed should be needed.
2. Add a before/after `learn` + `genie diff` step around a change (best demo).
3. Ansible applies standard configs, pyATS validates them; put both behind a pipeline or AWX/Semaphore so
   colleagues press a button instead of running CLI commands.
4. Look at Blitz (YAML-defined tests, in `genie.libs.sdk`) for colleagues who define tests but don't code.
5. Governance: someone owns the test library, standards repo and review process.
