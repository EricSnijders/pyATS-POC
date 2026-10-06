"""Topology-independent health checks. Loops over every device in the testbed,
asserts properties (not fixed values), and reads its rules from standards/standards.yaml."""
import re
from pathlib import Path

import yaml
from genie.metaparser.util.exceptions import SchemaEmptyParserError
from pyats import aetest

STANDARDS = Path(__file__).resolve().parent.parent / "standards" / "standards.yaml"


class CommonSetup(aetest.CommonSetup):
    @aetest.subsection
    def load_standards(self):
        self.parent.parameters["standards"] = yaml.safe_load(STANDARDS.read_text())

    @aetest.subsection
    def connect(self, testbed, steps):
        # every device gets its own step, so one unreachable device doesn't hide the rest
        self.parent.parameters["reachable"] = []
        for name, dev in testbed.devices.items():
            with steps.start(f"connect {name}", continue_=True) as step:
                dev.connect(log_stdout=False)
                self.parent.parameters["reachable"].append(dev)


def neighbor_states(node):
    """Collect every OSPF neighbour state, whatever the parser nesting
    ('show ip ospf neighbor' vs '... detail' differ per OS)."""
    found = []
    if isinstance(node, dict):
        for key, val in node.items():
            if key == "neighbors" and isinstance(val, dict):
                found += [(nid, n.get("state", "")) for nid, n in val.items()]
            else:
                found += neighbor_states(val)
    return found


class OspfNeighbors(aetest.Testcase):
    @aetest.test
    def full(self, steps, reachable, standards):
        want = standards["ospf"]["require_state"]
        for dev in reachable:
            with steps.start(dev.name, continue_=True) as step:
                out = None
                for cmd in ("show ip ospf neighbor", "show ip ospf neighbor detail"):
                    try:
                        out = dev.parse(cmd)
                        break
                    except SchemaEmptyParserError:
                        step.skipped("no OSPF neighbours")        # no OSPF here: not a failure
                    except Exception as e:                        # e.g. parser missing for this OS
                        last = e
                if out is None:
                    step.failed(f"no usable parser: {last}")
                bad = [(n, s) for n, s in neighbor_states(out) if not s.upper().startswith(want)]
                if bad:
                    step.failed(f"neighbours not {want}: {bad}")


class InterfaceHealth(aetest.Testcase):
    @aetest.test
    def admin_up_means_up(self, steps, reachable, standards):
        ignore = [re.compile(p) for p in standards["interfaces"]["ignore"]]
        for dev in reachable:
            with steps.start(dev.name, continue_=True) as step:
                intfs = dev.parse("show ip interface brief")["interface"]
                bad = [i for i, d in intfs.items()
                       if not any(p.search(i) for p in ignore)
                       and "administratively" not in d["status"]
                       and (d["status"] != "up" or d["protocol"] != "up")]
                if bad:
                    step.failed(f"admin-up but not up/up: {bad}")


class SoftwareVersion(aetest.Testcase):
    @aetest.test
    def allowed(self, steps, reachable, standards):
        for dev in reachable:
            with steps.start(dev.name, continue_=True) as step:
                allowed = standards["versions"].get(dev.os)
                if not allowed:
                    step.skipped(f"no version standard for os '{dev.os}'")
                ver = dev.parse("show version")["version"]["version"]
                if not any(ver.startswith(a) for a in allowed):
                    step.failed(f"{ver} not in {allowed}")


class CommonCleanup(aetest.CommonCleanup):
    @aetest.subsection
    def disconnect(self, reachable):
        for dev in reachable:
            dev.disconnect()


if __name__ == "__main__":
    aetest.main()
