"""Central version definition (Semantic Versioning: MAJOR.MINOR.PATCH[-prerelease])."""
__version__ = "2.0.0-dev"
APP_NAME = "GIS_BOX"
REPO = "GIS-GEORGIA/gis-toolkit"
RELEASES_API = "https://api.github.com/repos/{}/releases/latest".format(REPO)


def parse(v):
    """'2.0.0-dev' / 'v1.2.3' -> ((2, 0, 0), is_prerelease). ValueError if not semver."""
    import re
    m = re.match(r"^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+.*)?$", str(v).strip())
    if not m:
        raise ValueError(v)
    return (int(m[1]), int(m[2]), int(m[3])), bool(m[4])


def is_newer(candidate, current=__version__):
    """True if ``candidate`` is a higher version than ``current`` (a release beats its own prerelease)."""
    (a, pa), (b, pb) = parse(candidate), parse(current)
    return (a, not pa) > (b, not pb)
