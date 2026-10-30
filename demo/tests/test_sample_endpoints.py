"""Smoke tests for the endpoints that serve generated samples (task T2.6):
/f with real samples, /disguised, /cd variants and /index."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from starlette.testclient import TestClient

import make_samples
from demo_server.app import CD_VARIANTS, CONTENT_TYPES, create_app
from demo_server.config import DemoSettings


@pytest.fixture(scope="module")
def samples_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("samples")
    make_samples.write_samples(out)
    return out


@pytest.fixture
def client(samples_dir: Path, tmp_path: Path) -> Iterator[TestClient]:
    settings = DemoSettings(samples_dir=samples_dir, certs_dir=tmp_path / "certs")
    with TestClient(create_app(settings), base_url="http://a.demo.test:8081") as c:
        yield c


def test_genuine_samples_are_served_with_their_real_type(client: TestClient) -> None:
    r = client.get("/f/sample.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content.startswith(b"\x89PNG")


# Spec §11 disguises: the name, Content-Type and Content-Disposition all claim one thing.
@pytest.mark.parametrize(
    "name, content_type, real_start",
    [
        ("movie.mp4", "video/mp4", b"MZ"),
        ("invoice.pdf.exe", "application/vnd.microsoft.portable-executable", b"MZ"),
        ("photo.jpg", "image/jpeg", b"\x89PNG"),
        ("report.docx", CONTENT_TYPES[".docx"], b"PK\x03\x04"),
        ("file.pdf", "application/pdf", b"<!DOCTYPE html>"),
    ],
)
def test_disguised_samples_lie_in_their_headers(
    client: TestClient, name: str, content_type: str, real_start: bytes
) -> None:
    r = client.get(f"/disguised/{name}")
    assert r.status_code == 200
    assert r.headers["content-type"].split(";")[0] == content_type
    assert r.headers["content-disposition"] == f'attachment; filename="{name}"'
    assert r.content.startswith(real_start)


def test_disguised_supports_range(client: TestClient) -> None:
    r = client.get("/disguised/movie.mp4", headers={"Range": "bytes=0-1"})
    assert r.status_code == 206
    assert r.content == b"MZ"


@pytest.mark.parametrize("name", ["missing.mp4", "..", "..%2Fsample.exe", ".hidden"])
def test_disguised_unknown_or_escaping_names_are_404(client: TestClient, name: str) -> None:
    assert client.get(f"/disguised/{name}").status_code == 404


def test_genuine_folder_does_not_serve_disguised_files(client: TestClient) -> None:
    assert client.get("/f/movie.mp4").status_code == 404
    assert client.get("/f/disguised").status_code == 404


@pytest.mark.parametrize("variant", sorted(CD_VARIANTS))
def test_content_disposition_variants(client: TestClient, variant: str) -> None:
    header, sample = CD_VARIANTS[variant]
    r = client.get(f"/cd/{variant}")
    assert r.status_code == 200
    assert r.headers["content-disposition"] == header
    assert r.headers["content-type"] == "application/octet-stream"
    assert r.content == client.get(f"/f/{sample}").content


def test_cd_rtl_variant_hides_an_executable(client: TestClient) -> None:
    r = client.get("/cd/rtl")
    assert "%E2%80%AE" in r.headers["content-disposition"]
    assert r.content.startswith(b"MZ")


def test_cd_unknown_variant_lists_the_choices(client: TestClient) -> None:
    r = client.get("/cd/nope")
    assert r.status_code == 404
    assert "filename-star" in r.text


def test_missing_sample_behind_a_variant_says_how_to_fix_it(tmp_path: Path) -> None:
    empty = tmp_path / "samples"
    empty.mkdir()
    settings = DemoSettings(samples_dir=empty, certs_dir=tmp_path / "certs")
    with TestClient(create_app(settings)) as c:
        for path in ["/cd/quotes", "/disguised/movie.mp4"]:
            r = c.get(path)
            assert r.status_code == 404
            assert "make samples" in r.text


def test_index_is_an_html_folder_listing(client: TestClient) -> None:
    r = client.get("/index")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert r.text.startswith("<!doctype html>")
    assert '<a href="/f/sample.pdf">sample.pdf</a>' in r.text
    assert "disguised" not in r.text  # folders and disguised files are not listed
