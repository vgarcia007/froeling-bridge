#!/usr/bin/env python3
"""Build and optionally stage a private host setup bundle. No sudo/TTY actions.

The wheel is built by the caller. Database secrets are read from the existing
ignored .con file and written only to a mode-0700 bundle under .local.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile


def fields(path):
    result = {}
    for line in path.read_text().splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            result[key.strip().lower()] = value.strip()
    return result


def prepare(root, upload=False):
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    if status.stdout.strip():
        raise SystemExit("Commit the reviewed work before preparing a host release.")
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    bundle = root / ".local/host-test-bundle-0.3.0"
    if bundle.exists():
        raise SystemExit("Private bundle already exists; inspect it before rebuilding.")
    bundle.mkdir(mode=0o700, parents=True)
    wheel = root / ".local/wheels/froeling_bridge-0.3.0-py3-none-any.whl"
    if not wheel.is_file():
        raise SystemExit("Build the 0.3.0 wheel into .local/wheels first.")
    import zipfile

    with zipfile.ZipFile(wheel) as package:
        for path in (root / "src/froeling_bridge").rglob("*"):
            if path.is_file() and path.suffix in (
                ".py",
                ".json",
                ".css",
                ".js",
                ".html",
            ):
                name = (
                    "froeling_bridge/"
                    + path.relative_to(root / "src/froeling_bridge").as_posix()
                )
                if package.read(name) != path.read_bytes():
                    raise SystemExit(
                        "Project wheel is stale; rebuild it from the reviewed checkout."
                    )
    (bundle / "release.json").write_text(
        json.dumps(
            dict(version="0.3.0", commit=commit, python="3.12", architecture="x86_64")
        )
        + "\n"
    )
    shutil.copytree(root / "deploy/systemd", bundle / "systemd")
    for name in (
        "install.sh",
        "install_state.py",
        "update-lan.sh",
        "repair-test.sh",
        "froeling-bridge-test",
    ):
        shutil.copy2(root / "deploy" / name, bundle / name)
    wheels = bundle / "wheels"
    wheels.mkdir()
    subprocess.run(
        [
            str(root / ".venv/bin/python"),
            "-m",
            "pip",
            "download",
            "--index-url",
            "https://pypi.org/simple",
            "--only-binary=:all:",
            "--platform",
            "manylinux2014_x86_64",
            "--python-version",
            "312",
            "--implementation",
            "cp",
            "--abi",
            "cp312",
            "--dest",
            str(wheels),
            str(wheel) + "[service]",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    source = fields(root / "live-db.con")
    host = source["host"]
    port = 3306
    if host.count(":") == 1:
        host, raw_port = host.rsplit(":", 1)
        port = int(raw_port)
    config = dict(
        host=host,
        port=port,
        database=source["dbname"],
        user=source["user"],
        password=source["password"],
    )
    path = bundle / "source-db.json"
    path.write_text(json.dumps(config) + "\n")
    path.chmod(0o600)
    # Verify the source connection shape without connecting to the live DB.
    from froeling_bridge.storage import DatabaseConfig

    DatabaseConfig.load(path)
    manifest = []
    for path in sorted(bundle.rglob("*")):
        if path.is_file():
            manifest.append(
                hashlib.sha256(path.read_bytes()).hexdigest()
                + "  "
                + path.relative_to(bundle).as_posix()
            )
    (bundle / "SHA256SUMS").write_text("\n".join(manifest) + "\n")
    if upload:
        ssh = fields(root / "live-server-ssh.con")
        args = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=7",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "UserKnownHostsFile=" + str(root / ".local/ssh_known_hosts"),
        ]
        auth = ssh.get("auth", "")
        if auth and Path(auth).expanduser().is_file():
            args += ["-i", str(Path(auth).expanduser())]
        args += [ssh["user"] + "@" + ssh["host"]]
        archive = root / ".local/host-test-bundle-0.3.0.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            for path in sorted(bundle.rglob("*")):
                tar.add(path, arcname=path.relative_to(bundle), recursive=False)
        archive.chmod(0o600)
        # Fixed new directory under the remote user's home. Never overwrite an
        # existing setup, touch p4d or run anything from the uploaded package.
        command = 'umask 077; mkdir "$HOME/froeling-bridge-test-0.3.0" && tar -xzf - -C "$HOME/froeling-bridge-test-0.3.0"'
        with archive.open("rb") as stream:
            subprocess.run(
                args + [command], stdin=stream, check=True, stdout=subprocess.DEVNULL
            )
        print(
            "Private setup bundle staged. No services, databases or TTY settings changed on the host."
        )
    else:
        print("Private host setup bundle prepared under .local; not uploaded.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upload", action="store_true")
    arguments = parser.parse_args()
    prepare(Path(__file__).resolve().parents[2], arguments.upload)
