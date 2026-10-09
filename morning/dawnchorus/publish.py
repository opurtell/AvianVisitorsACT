"""Publish the rendered site.

github-pages: the output directory (editions/) is a clone of the public
Pages repo. Commit whatever changed and push. On greg the clone's remote
is an ssh alias with a repo-scoped deploy key, so the push can reach that
one repo and nothing else.

Nothing here runs scrub: every page was checked when it was rendered.
"""

import subprocess
from pathlib import Path


class PublishError(RuntimeError):
    pass


def git(site, *args):
    proc = subprocess.run(["git", "-C", str(site), *args], capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise PublishError(f"git {' '.join(args)}: {(proc.stderr or proc.stdout).strip()}")
    return proc.stdout


def github_pages(site, message):
    """Commit and push; returns False when there was nothing to publish."""
    site = Path(site)
    if not (site / ".git").exists():
        raise PublishError(f"{site} is not a git checkout of the Pages repo")
    (site / ".nojekyll").touch()          # serve files as-is, no Jekyll build
    git(site, "add", "-A")
    if not git(site, "status", "--porcelain"):
        return False
    git(site, "commit", "-q", "-m", message)
    git(site, "push", "-q", "origin", "HEAD")
    return True


def publish(target, site, message):
    if target == "github-pages":
        return github_pages(site, message)
    raise PublishError(f"publish target {target!r} is not supported (see PLAN.md, Publishing)")
