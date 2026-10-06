"""pyats run job jobs/health_job.py --testbed-file testbeds/<env>.yaml"""
from pathlib import Path

from pyats.easypy import run

TESTS = Path(__file__).resolve().parent.parent / "tests"


def main(runtime):
    run(testscript=str(TESTS / "health_checks.py"), runtime=runtime, taskid="health")
