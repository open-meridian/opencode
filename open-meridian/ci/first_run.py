"""First run for the CI deployment, with no platform.

A deployment is normally set up by its first-run wizard, opened with a code the
platform issues. CI has no platform, so this writes what the released chart
reads once first run is done -- the names below are the chart's own values and
Secret keys -- and restarts what reads them:

- the database the chart brings, started, with a serving and a migrating role;
- the database Secret, holding both URLs;
- the addresses Secret: the dashboard's address, and one account the
  deployment holds itself, named as its administrator, with a password hash.

The password is drawn here, written to a file only its owner reads, and never
printed. That account is the one person the run signs in as.

Usage: python3 first_run.py RUN_DIR
Reads KUBECONFIG. Standard library, plus argon2-cffi for the hash.
"""

import base64
import json
import os
import secrets
import subprocess
import sys
import time

from argon2 import PasswordHasher

NAMESPACE = "meridian"
RELEASE = "meridian"
FULL = f"{RELEASE}-meridian-runtime"
ADDRESS = "http://meridian.localhost"
PERSON = "pat"


def kubectl(*args, stdin=None, check=True, quiet=False):
    done = subprocess.run(["kubectl", "--namespace", NAMESPACE, *args],
                          input=stdin, capture_output=True)
    if check and done.returncode != 0:
        said = "(not shown: it can quote a password)" if quiet else done.stderr.decode(errors="replace")
        sys.exit(f"first run: kubectl {args[0]} failed: {said}")
    return done


def text(*args):
    return kubectl(*args).stdout.decode().strip()


def wait(what, ready, seconds=600):
    start = time.time()
    print(f"first run: waiting for {what}, at most {seconds}s", flush=True)
    while time.time() - start < seconds:
        try:
            if ready():
                return
        except Exception:
            pass
        time.sleep(3)
    sys.exit(f"first run: {what} never happened in {seconds}s")


def b64(value):
    return base64.b64encode(value.encode()).decode()


def psql(sql, database="meridian"):
    kubectl("exec", "-i", f"{FULL}-database-0", "-c", "postgres", "--",
            "psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", database,
            stdin=sql.encode(), quiet=True)


def replace_secret(name, data):
    current = json.loads(text("get", "secret", name, "-o", "json"))
    current["data"] = {key: b64(value) for key, value in data.items()}
    kubectl("replace", "-f", "-", stdin=json.dumps(current).encode(), quiet=True)


def main():
    run_dir = sys.argv[1]

    # The database the chart brings starts with no member until first run.
    wait("the database StatefulSet", lambda: kubectl(
        "get", "statefulset", f"{FULL}-database", check=False).returncode == 0)
    kubectl("scale", "statefulset", f"{FULL}-database", "--replicas=1")
    wait("the database", lambda: kubectl(
        "exec", f"{FULL}-database-0", "-c", "postgres", "--", "pg_isready", "-h", "127.0.0.1",
        "-U", "postgres", check=False).returncode == 0)

    passwords = json.loads(text("get", "secret", f"{FULL}-database-passwords", "-o", "json"))["data"]
    serving = base64.b64decode(passwords["serving"]).decode()
    migrating = base64.b64decode(passwords["migrating"]).decode()
    psql(f"create role meridian_app login password '{serving}';\n"
         f"create role meridian_migrate login password '{migrating}';\n"
         "create database meridian;\n", database="postgres")
    psql("grant connect on database meridian to meridian_app, meridian_migrate;\n"
         "grant usage on schema public to meridian_app, meridian_migrate;\n"
         "grant create on schema public to meridian_migrate;\n"
         "revoke create on schema public from meridian_app, public;\n")
    host = f"{FULL}-database.{NAMESPACE}.svc.cluster.local"
    replace_secret(f"{FULL}-database", {
        "url": f"postgres://meridian_app:{serving}@{host}:5432/meridian?sslmode=disable",
        "migrate-url": f"postgres://meridian_migrate:{migrating}@{host}:5432/meridian?sslmode=disable",
    })
    del serving, migrating, passwords

    # The one person: an account this deployment holds, and its administrator.
    password = secrets.token_urlsafe(24)
    hashed = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1).hash(password)
    replace_secret("meridian-addresses", {
        "dashboard-url": ADDRESS,
        "local-accounts": "on",
        "local-account-name": PERSON,
        "administrator-login": f"local|{PERSON}",
        "administrator-display-name": "Pat Example",
        "administrator-password-hash": hashed,
    })
    person = os.path.join(run_dir, "person.json")
    with open(os.open(person, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as kept:
        json.dump({"name": PERSON, "password": password}, kept)
    del password

    # What the first-run Job does once its Secrets are written: restart what
    # reads them at start, finish, and give up its own rights.
    jobs = json.loads(text("get", "jobs", "-o", "json"))["items"]
    job = next(j for j in jobs
               if j["spec"]["template"]["metadata"]["labels"].get("meridian.dev/component") == "first-run")
    env = {e["name"]: e.get("value", "") for e in job["spec"]["template"]["spec"]["containers"][0].get("env", [])}
    restart = [name.strip() for name in env.get("MERIDIAN_FIRST_RUN_RESTART", "").split(",") if name.strip()]
    for name in restart:
        kubectl("rollout", "restart", f"deployment/{name}")
    kubectl("delete", "pod", "-l", f"job-name={job['metadata']['name']}", "--wait")
    wait("the first-run Job to finish", lambda: json.loads(text(
        "get", "job", job["metadata"]["name"], "-o", "json"))["status"].get("succeeded"), seconds=180)
    if env.get("MERIDIAN_FIRST_RUN_BINDING"):
        kubectl("delete", "rolebinding", env["MERIDIAN_FIRST_RUN_BINDING"], "--ignore-not-found")
    for name in restart:
        kubectl("rollout", "status", f"deployment/{name}", "--timeout=600s")

    def every_deployment_available():
        names = text("get", "deployments", "-o", "name").split()
        return names and kubectl("wait", "--for=condition=Available", "--timeout=5s", *names,
                                 check=False).returncode == 0
    wait("every component", every_deployment_available, seconds=900)
    print("first run: done; one person, signed in as", PERSON, flush=True)


if __name__ == "__main__":
    main()
