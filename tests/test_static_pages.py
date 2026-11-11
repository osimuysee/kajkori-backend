"""The static pages are served from two places: the API server (/, /login,
/static/login.html ...) and GitHub Pages (/kajkori-backend/static/...). A link
or redirect that starts with "/" works on the first and is a 404 on the second,
which is what broke the page after login. Keep every in-site link relative."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "static"
PAGES = sorted(STATIC_DIR.glob("*.html"))

# href="/..." or src="/..." (but not protocol-relative "//host/...").
ROOT_ABSOLUTE_ATTR = re.compile(r"""(?:href|src|action)\s*=\s*["']/(?!/)""")
# location.href = "/..." , location.replace("/...") , location.assign('/...')
ROOT_ABSOLUTE_REDIRECT = re.compile(r"""location(?:\.href)?\s*(?:=|\.(?:replace|assign)\()\s*["'`]/(?!/)""")
# Any quoted "/" or "/page" used as a navigation target constant.
ROOT_ABSOLUTE_CONST = re.compile(r"""[?:=]\s*["']/(?:admin|login|register|index|static)?(?:\.html)?["']""")
LOCAL_LINK = re.compile(r"""(?:href|src)\s*=\s*["']([^"'#?:]+\.(?:html|css|js))(?:[?#][^"']*)?["']""")


def test_there_are_static_pages():
    assert PAGES, "static/*.html not found"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_no_root_absolute_links_or_redirects(page):
    text = page.read_text(encoding="utf-8")
    code_lines = [line for line in text.splitlines() if not line.strip().startswith("//")]
    code = "\n".join(code_lines)
    for pattern in (ROOT_ABSOLUTE_ATTR, ROOT_ABSOLUTE_REDIRECT, ROOT_ABSOLUTE_CONST):
        found = pattern.findall(code)
        assert not found, f"{page.name}: root-absolute link/redirect {found!r} breaks on GitHub Pages"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_local_links_point_at_existing_files(page):
    text = page.read_text(encoding="utf-8")
    for target in LOCAL_LINK.findall(text):
        if "${" in target:
            continue
        assert (page.parent / target).exists(), f"{page.name} links to missing file {target}"


def test_relative_page_links_work_on_the_api_server(api):
    # login.html redirects to "index.html" / "admin.html"; from /login and from
    # /static/login.html both must resolve to a page the server really serves.
    for path in ("/index.html", "/admin.html", "/login.html", "/register.html",
                 "/static/index.html", "/static/admin.html", "/static/login.html",
                 "/static/register.html"):
        assert api.client.get(path).status_code == 200, path


def test_github_pages_root_redirects_to_the_site():
    root_index = ROOT / "index.html"
    assert root_index.exists()
    assert 'url=static/index.html' in root_index.read_text(encoding="utf-8")
