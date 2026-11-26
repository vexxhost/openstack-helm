# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pyyaml",
# ]
# ///
"""Publish the charts of a vexxhost/openstack-helm branch to GHCR.

Run by .github/workflows/publish.yaml, which the openstack-helm-publish Zuul
job triggers after every merge to master or stable/* (see docs/forks.md in
vexxhost/images). This file is a downstream carry on master only.

Every directory with a Chart.yaml is packaged and pushed to
oci://ghcr.io/vexxhost/openstack-helm/<chart> unless that version is already
there. There is no versioning scheme of our own:

* Branches that have upstream's tools/chart_version.sh (master and branches
  cut from it) use it, which gives <base>.<commits since tag>+<sha> from the
  chart's own history. Upstream's tags must be fetched for the count.
* Other branches (imported ones, such as stable/2026.1) use the version in
  Chart.yaml plus the short SHA of the last commit that touched the chart (or
  the shared helm-toolkit/ it depends on), for example 0.3.23+1a2b3c4d5.

OCI tags can't contain "+", so Helm stores 0.3.23+1a2b3c4d5 as the tag
0.3.23_1a2b3c4d5. New pushes are signed with cosign (keyless, GitHub Actions
OIDC). Every chart is also tagged with the full SHA of the branch commit that
was published, so all charts of a commit can be resolved with
ghcr.io/vexxhost/openstack-helm/<chart>:<commit>.

A chart that fails is reported and the others still publish; the exit status
is non-zero if any chart failed.

Usage:
  uv run .github/scripts/publish.py --fork <checkout of the branch> --dry-run
  uv run .github/scripts/publish.py --fork <checkout of the branch>
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

REGISTRY = "ghcr.io/vexxhost/openstack-helm"
PLAIN_HTTP: list[str] = []  # --plain-http, for testing against a local registry
SHARED_TOOLKIT = "helm-toolkit"
SUBCOMMAND_TIMEOUT = 600


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def run(cmd: list[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True,
                            timeout=SUBCOMMAND_TIMEOUT)
    if check and result.returncode != 0:
        raise RuntimeError(
            f"{' '.join(cmd)} failed ({result.returncode}):\n{result.stdout}{result.stderr}"
        )
    return result


def charts(fork: Path) -> list[str]:
    return sorted(p.parent.name for p in fork.glob("*/Chart.yaml"))


def dependencies(chart_dir: Path) -> list[dict]:
    chart = yaml.safe_load((chart_dir / "Chart.yaml").read_text()) or {}
    deps = list(chart.get("dependencies") or [])
    requirements = chart_dir / "requirements.yaml"
    if requirements.exists():
        deps += (yaml.safe_load(requirements.read_text()) or {}).get("dependencies") or []
    return deps


def local_dependencies(fork: Path, name: str) -> list[str]:
    """Sibling chart directories a chart depends on through file://."""
    paths = []
    for dep in dependencies(fork / name):
        repository = str(dep.get("repository", ""))
        if repository.startswith("file://"):
            target = (fork / name / repository[len("file://"):]).resolve()
            paths.append(target.relative_to(fork.resolve()).as_posix())
    return paths


def base_version(fork: Path) -> str:
    match = re.search(r"^BASE_VERSION\s*\??=\s*(\S+)", (fork / "Makefile").read_text(), re.M)
    if not match:
        raise RuntimeError("BASE_VERSION not found in Makefile")
    return match.group(1)


def chart_version(fork: Path, name: str) -> str:
    script = fork / "tools" / "chart_version.sh"
    if script.exists():
        return run(["bash", str(script), name, base_version(fork)], cwd=fork).stdout.strip()
    chart = yaml.safe_load((fork / name / "Chart.yaml").read_text())
    version = str(chart["version"]).split("+", 1)[0]
    paths = [name, *local_dependencies(fork, name)]
    sha = run(["git", "log", "-1", "--abbrev=9", "--format=%h", "--", *paths],
              cwd=fork).stdout.strip()
    if not sha:
        raise RuntimeError(f"no commit touches {' '.join(paths)}")
    return f"{version}+{sha}"


def oci_tag(version: str) -> str:
    return version.replace("+", "_")


def exists(name: str, tag: str) -> bool:
    return run(["oras", "manifest", "fetch", *PLAIN_HTTP, "--descriptor", f"{REGISTRY}/{name}:{tag}"],
               check=False).returncode == 0


def package(fork: Path, name: str, version: str, workdir: Path) -> Path:
    if local_dependencies(fork, name):
        run(["helm", "dependency", "build", str(fork / name)])
    out = run(["helm", "package", str(fork / name), "--version", version,
               "-d", str(workdir)]).stdout
    return Path(out.strip().rsplit(": ", 1)[1])


def push(package_path: Path, name: str, tag: str) -> str:
    out = run(["helm", "push", *PLAIN_HTTP, str(package_path), f"oci://{REGISTRY}"])
    match = re.search(r"Digest:\s*(sha256:[0-9a-f]{64})", out.stdout + out.stderr)
    if match:
        return match.group(1)
    descriptor = run(["oras", "manifest", "fetch", *PLAIN_HTTP, "--descriptor",
                      f"{REGISTRY}/{name}:{tag}"]).stdout
    match = re.search(r'"digest":\s*"(sha256:[0-9a-f]{64})"', descriptor)
    if not match:
        raise RuntimeError(f"cannot find the digest of {name}:{tag}")
    return match.group(1)


def clean(fork: Path, name: str) -> None:
    """Remove what `helm dependency build` leaves in the checkout."""
    for dep in local_dependencies(fork, name):
        archive_dir = fork / name / "charts"
        for archive in archive_dir.glob(f"{Path(dep).name}-*.tgz"):
            archive.unlink()
    for lock in ("requirements.lock", "Chart.lock"):
        lock_path = fork / name / lock
        tracked = run(["git", "ls-files", "--error-unmatch", str(lock_path)], cwd=fork,
                      check=False).returncode == 0
        if lock_path.exists() and not tracked:
            lock_path.unlink()


def main() -> None:
    global REGISTRY
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--fork", type=Path, required=True,
                        help="vexxhost/openstack-helm checkout at the commit to publish")
    parser.add_argument("--dry-run", action="store_true",
                        help="package every chart without pushing, tagging or signing")
    parser.add_argument("--no-sign", action="store_true", help="skip cosign signing")
    parser.add_argument("--chart", action="append", help="only these charts")
    parser.add_argument("--registry", default=REGISTRY,
                        help=f"repository prefix to publish to (default: {REGISTRY})")
    parser.add_argument("--plain-http", action="store_true",
                        help="use HTTP, for testing against a local registry")
    args = parser.parse_args()

    REGISTRY = args.registry
    if args.plain_http:
        PLAIN_HTTP.append("--plain-http")

    fork = args.fork.resolve()
    commit = run(["git", "rev-parse", "HEAD"], cwd=fork).stdout.strip()
    selected = args.chart or charts(fork)
    results, failed = [], []

    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        for name in selected:
            try:
                version = chart_version(fork, name)
                tag = oci_tag(version)
                if args.dry_run:
                    package(fork, name, version, workdir)
                    results.append((name, version, "packaged"))
                elif exists(name, tag):
                    results.append((name, version, "exists"))
                else:
                    digest = push(package(fork, name, version, workdir), name, tag)
                    if not args.no_sign:
                        run(["cosign", "sign", "--yes", f"{REGISTRY}/{name}@{digest}"])
                    results.append((name, version, f"pushed {digest}"))
                if not args.dry_run:
                    run(["oras", "tag", *PLAIN_HTTP, f"{REGISTRY}/{name}:{tag}", commit])
            except (RuntimeError, subprocess.TimeoutExpired) as error:
                failed.append(name)
                results.append((name, "-", "FAILED"))
                log(f"::error title={name}::{error}")
            finally:
                clean(fork, name)
                for leftover in workdir.glob("*.tgz"):
                    leftover.unlink()
            log(f"{name}: {results[-1][1]} {results[-1][2]}")

    print(f"Published {REGISTRY} from {commit}\n")
    print("| Chart | Version | Result |")
    print("| -- | -- | -- |")
    for name, version, status in results:
        print(f"| {name} | `{version}` | {status} |")
    if failed:
        raise SystemExit(f"failed: {', '.join(failed)}")


if __name__ == "__main__":
    main()
