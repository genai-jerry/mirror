"""The system test data loader — `backend/scripts/test_data.py`.

The loader's job is to put this epic's configuration sets into a *running*
backend, so these tests run it against a real one: the client they hand it is a
`TestClient` over the real app with the admin surface switched on, and what they
assert on afterwards is the configuration the backend then answers from.

The sets themselves are the real ones in the checkout, found wherever the epic's
change folder sits, because "the records in this repository load" is the thing
worth proving. The refusals are driven from data directories a test writes
itself, so each one holds exactly the one fault under test.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import test_data
from conftest import ADMIN_TOKEN
from fastapi.testclient import TestClient

from app.config import load_config, override_path
from app.languages import load_language_config
from app.main import create_app
from app.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]

#: The sets this epic's plan names, and the configuration file each replaces.
LOADABLE = [
    pytest.param("baseline", "languages", id="baseline languages"),
    pytest.param("add-tamil", "languages", id="Tamil added"),
    pytest.param("provider-change", "languages", id="translation provider changed"),
    pytest.param("low-budget", "budget", id="low recognition budget"),
]


@pytest.fixture(scope="session")
def data_dir() -> Path:
    """The epic's data directory in this checkout, wherever its change folder sits.

    Found rather than written down, so archiving the change (which moves the
    folder) does not turn this suite red.
    """
    for candidate in sorted(REPO_ROOT.glob("openspec/changes/**/system-tests/data")):
        if not candidate.is_dir():
            continue
        if test_data.STARTING_SET in test_data.read_sets(candidate):
            return candidate
    pytest.fail(
        "no system test data directory in this checkout holds a "
        f"{test_data.STARTING_SET} set — see openspec/changes/*/system-tests/data"
    )


@pytest.fixture
def loader_client(admin_settings: Settings) -> Iterator[TestClient]:
    """A running backend with the admin surface on, and the token to call it."""
    with TestClient(
        create_app(admin_settings),
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
    ) as client:
        yield client


def _written(name: str, settings: Settings) -> dict[str, Any]:
    """The override file the backend now answers `<name>.json` from."""
    return json.loads(override_path(name, settings).read_text(encoding="utf-8"))


def _data_dir_holding(tmp_path: Path, *sets: dict[str, Any]) -> Path:
    """A data directory holding exactly the set files a test gives it."""
    directory = tmp_path / "data"
    directory.mkdir()
    for index, payload in enumerate(sets, start=1):
        name = payload.get("set") or f"DS-{index}"
        (directory / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")
    return directory


# --- what each set does to the backend -------------------------------------


@pytest.mark.parametrize(("set_name", "config_name"), LOADABLE)
def test_every_set_the_plan_names_is_accepted_by_the_backend(
    loader_client: TestClient,
    admin_settings: Settings,
    data_dir: Path,
    set_name: str,
    config_name: str,
) -> None:
    """Each set maps onto a whole configuration file the running backend will store."""
    said = test_data.load(loader_client, data_dir, set_name)

    assert said == [f"{set_name} is now the {config_name} configuration"]
    assert override_path(config_name, admin_settings).is_file()
    # It is readable as configuration, which is what the next request needs.
    load_config(config_name, admin_settings)


def test_the_baseline_set_offers_malayalam_into_english(
    loader_client: TestClient, admin_settings: Settings, data_dir: Path
) -> None:
    test_data.load(loader_client, data_dir, "baseline")

    languages = load_language_config(admin_settings)
    assert [source.code for source in languages.sources] == ["ml-IN"]
    assert [target.code for target in languages.targets] == ["en-IN"]
    assert languages.source("ml-IN").name == "Malayalam"
    assert languages.recognition_provider_for("ml-IN").name == "sarvam-parse"
    assert languages.translation_provider_for("ml-IN").name == "sarvam-translate"


def test_the_tamil_set_adds_tamil_to_what_the_picker_shows(
    loader_client: TestClient, data_dir: Path
) -> None:
    """ST-7: a language added to the configuration appears, with no app release."""
    before = loader_client.get("/v1/languages").json()
    assert [source["code"] for source in before["sources"]] == ["ml-IN"]

    test_data.load(loader_client, data_dir, "add-tamil")

    after = loader_client.get("/v1/languages").json()
    assert after["sources"] == [
        {"code": "ml-IN", "name": "Malayalam"},
        {"code": "ta-IN", "name": "Tamil"},
    ]


def test_the_provider_change_set_points_malayalam_at_the_alternate_entry(
    loader_client: TestClient, admin_settings: Settings, data_dir: Path
) -> None:
    """ST-8: translation moves to the alternate entry; recognition does not move."""
    test_data.load(loader_client, data_dir, "provider-change")

    languages = load_language_config(admin_settings)
    assert languages.translation_provider_for("ml-IN").name == "sarvam-translate-alt"
    assert languages.recognition_provider_for("ml-IN").name == "sarvam-parse"


def test_the_low_budget_set_cuts_the_recognition_budget_and_keeps_the_rest(
    loader_client: TestClient, admin_settings: Settings, data_dir: Path
) -> None:
    """ST-6: two recognition calls a minute, and every other budget field as shipped."""
    shipped = dict(test_data.shipped_config("budget"))

    test_data.load(loader_client, data_dir, "low-budget")

    budget = load_config("budget", admin_settings)
    assert budget["recognition_per_minute"] == 2
    assert budget["translation_per_minute"] == 60
    assert budget["max_wait_seconds"] == shipped["max_wait_seconds"]
    assert budget["translation_cache_seconds"] == shipped["translation_cache_seconds"]


def test_a_set_replaces_the_shipped_file_rather_than_adding_to_it(
    loader_client: TestClient, admin_settings: Settings, data_dir: Path
) -> None:
    """An override is a whole file, so the budget it writes has every field."""
    test_data.load(loader_client, data_dir, "low-budget")

    assert set(_written("budget", admin_settings)) == set(test_data.shipped_config("budget"))


# --- loading twice, and starting over --------------------------------------


@pytest.mark.parametrize(("set_name", "config_name"), LOADABLE)
def test_loading_a_set_twice_leaves_exactly_what_loading_it_once_left(
    loader_client: TestClient,
    admin_settings: Settings,
    data_dir: Path,
    set_name: str,
    config_name: str,
) -> None:
    """Idempotent: a second load writes the same file, it does not stack a second."""
    test_data.load(loader_client, data_dir, set_name)
    once = _written(config_name, admin_settings)

    test_data.load(loader_client, data_dir, set_name)

    assert _written(config_name, admin_settings) == once
    assert sorted(path.name for path in admin_settings.config_dir.iterdir()) == [
        f"{config_name}.json"
    ]


def test_loading_with_no_set_named_starts_the_epic_from_the_baseline(
    loader_client: TestClient, admin_settings: Settings, data_dir: Path
) -> None:
    """What the release runs after a deploy: nothing left over, baseline in force."""
    test_data.load(loader_client, data_dir, "low-budget")

    said = test_data.load(loader_client, data_dir)

    assert said == [
        "removed the budget.json override; the shipped configuration is back",
        "baseline is now the languages configuration",
    ]
    assert load_config("budget", admin_settings) == test_data.shipped_config("budget")
    assert [source.code for source in load_language_config(admin_settings).sources] == ["ml-IN"]


def test_loading_with_no_set_named_twice_says_the_second_time_found_nothing(
    loader_client: TestClient, data_dir: Path
) -> None:
    test_data.load(loader_client, data_dir)

    assert test_data.load(loader_client, data_dir) == [
        "removed the languages.json override; the shipped configuration is back",
        "baseline is now the languages configuration",
    ]


def test_one_set_leaves_the_other_configuration_file_alone(
    loader_client: TestClient, admin_settings: Settings, data_dir: Path
) -> None:
    """A tester lowering the budget for ST-6 does not lose the languages they set."""
    test_data.load(loader_client, data_dir, "add-tamil")
    test_data.load(loader_client, data_dir, "low-budget")

    codes = [source.code for source in load_language_config(admin_settings).sources]
    assert codes == ["ml-IN", "ta-IN"]
    assert load_config("budget", admin_settings)["recognition_per_minute"] == 2


# --- taking it out again ---------------------------------------------------


def test_unload_puts_the_shipped_configuration_back(
    loader_client: TestClient, admin_settings: Settings, data_dir: Path
) -> None:
    test_data.load(loader_client, data_dir, "add-tamil")
    test_data.load(loader_client, data_dir, "low-budget")

    said = test_data.unload(loader_client, data_dir)

    assert said == [
        "removed the budget.json, languages.json override; the shipped configuration is back"
    ]
    assert list(admin_settings.config_dir.iterdir()) == []
    assert load_config("languages", admin_settings) == test_data.shipped_config("languages")
    assert load_config("budget", admin_settings) == test_data.shipped_config("budget")


def test_unload_with_nothing_loaded_says_so_rather_than_failing(
    loader_client: TestClient, data_dir: Path
) -> None:
    """Idempotent in the direction that matters when a run is repeated."""
    assert test_data.unload(loader_client, data_dir) == [
        "no override was in place; the shipped configuration is in force"
    ]


# --- what the loader refuses ----------------------------------------------


def test_a_set_name_that_is_not_here_names_the_ones_that_are(
    loader_client: TestClient, data_dir: Path
) -> None:
    with pytest.raises(test_data.LoaderError) as refused:
        test_data.load(loader_client, data_dir, "no-such-set")

    message = str(refused.value)
    assert "no-such-set" in message
    assert "add-tamil" in message
    assert "low-budget" in message


@pytest.mark.parametrize("set_name", ["H1", "unsupported-language-request"])
def test_a_tester_side_set_is_refused_because_nothing_loads_it(
    loader_client: TestClient, data_dir: Path, set_name: str
) -> None:
    """DS-1 and DS-4 are used straight from the checkout, as test-data.md says."""
    with pytest.raises(test_data.LoaderError, match="straight from the checkout"):
        test_data.load(loader_client, data_dir, set_name)


@pytest.mark.parametrize("command", [test_data.load, test_data.unload])
def test_a_data_directory_that_is_not_there_is_named(
    loader_client: TestClient, tmp_path: Path, command: Any
) -> None:
    missing = tmp_path / "nowhere"

    with pytest.raises(test_data.LoaderError, match=str(missing)):
        command(loader_client, missing)


def test_a_record_field_the_loader_does_not_know_stops_the_load(
    loader_client: TestClient, tmp_path: Path
) -> None:
    """A data set and the loader have to change together, so silence would be wrong."""
    directory = _data_dir_holding(
        tmp_path,
        {
            "set": "DS-3",
            "records": [{"id": "low-budget", "recognition_requests_per_hour": 2}],
        },
    )

    with pytest.raises(test_data.LoaderError, match="recognition_requests_per_hour"):
        test_data.load(loader_client, directory, "low-budget")


def test_a_provider_the_loader_cannot_map_stops_the_load(
    loader_client: TestClient, tmp_path: Path
) -> None:
    directory = _data_dir_holding(
        tmp_path,
        {
            "set": "DS-2",
            "records": [
                {
                    "id": "baseline",
                    "source_languages": ["ml-IN"],
                    "target_languages": ["en-IN"],
                    "providers": {"ml-IN": {"recognition": "nobody", "translation": "sarvam"}},
                }
            ],
        },
    )

    with pytest.raises(test_data.LoaderError, match="nobody is not a recognition provider"):
        test_data.load(loader_client, directory, "baseline")


def test_a_source_language_with_no_providers_stops_the_load(
    loader_client: TestClient, tmp_path: Path
) -> None:
    directory = _data_dir_holding(
        tmp_path,
        {
            "set": "DS-2",
            "records": [
                {
                    "id": "baseline",
                    "source_languages": ["ml-IN", "ta-IN"],
                    "target_languages": ["en-IN"],
                    "providers": {"ml-IN": {"recognition": "sarvam", "translation": "sarvam"}},
                }
            ],
        },
    )

    with pytest.raises(test_data.LoaderError, match="ta-IN names no providers"):
        test_data.load(loader_client, directory, "baseline")


def test_a_data_file_that_is_not_valid_json_is_named(
    loader_client: TestClient, tmp_path: Path
) -> None:
    directory = tmp_path / "data"
    directory.mkdir()
    (directory / "DS-2.json").write_text("{not json", encoding="utf-8")

    with pytest.raises(test_data.LoaderError, match="DS-2.json is not valid JSON"):
        test_data.load(loader_client, directory, "baseline")


def test_two_sets_with_the_same_record_name_are_refused(
    loader_client: TestClient, tmp_path: Path
) -> None:
    """`--set` takes a record name, so two records cannot share one."""
    directory = _data_dir_holding(
        tmp_path,
        {"set": "DS-2", "records": [{"id": "baseline"}]},
        {"set": "DS-3", "records": [{"id": "baseline"}]},
    )

    with pytest.raises(test_data.LoaderError, match="both hold a record called baseline"):
        test_data.load(loader_client, directory, "baseline")


def test_an_empty_data_directory_is_refused(loader_client: TestClient, tmp_path: Path) -> None:
    directory = tmp_path / "data"
    directory.mkdir()

    with pytest.raises(test_data.LoaderError, match="no DS-\\*.json"):
        test_data.load(loader_client, directory)


# --- what the backend refuses --------------------------------------------


def test_a_backend_started_without_an_admin_token_is_explained(
    client: TestClient, data_dir: Path
) -> None:
    """ADMIN_TOKEN unset on the backend: the endpoints answer 404, not 401."""
    client.headers["Authorization"] = f"Bearer {ADMIN_TOKEN}"

    with pytest.raises(test_data.LoaderError, match="without ADMIN_TOKEN set"):
        test_data.load(client, data_dir, "baseline")


def test_a_token_the_backend_does_not_accept_is_explained(
    admin_client: TestClient, data_dir: Path
) -> None:
    admin_client.headers["Authorization"] = "Bearer not-the-admin-token"

    with pytest.raises(test_data.LoaderError, match="refused the token in ADMIN_TOKEN"):
        test_data.load(admin_client, data_dir, "baseline")


def test_a_configuration_the_backend_will_not_store_is_reported_in_its_own_words(
    loader_client: TestClient, tmp_path: Path
) -> None:
    """The backend validates a whole file before storing it; the loader relays why."""
    directory = _data_dir_holding(
        tmp_path,
        {
            "set": "DS-2",
            "records": [
                {
                    "id": "baseline",
                    "source_languages": ["ml-IN", "ML-in"],
                    "target_languages": ["en-IN"],
                    "providers": {
                        "ml-IN": {"recognition": "sarvam", "translation": "sarvam"},
                        "ML-in": {"recognition": "sarvam", "translation": "sarvam"},
                    },
                }
            ],
        },
    )

    with pytest.raises(test_data.LoaderError, match="invalid_configuration") as refused:
        test_data.load(loader_client, directory, "baseline")

    assert "configured twice" in str(refused.value)


# --- the command line ----------------------------------------------------


def test_the_command_line_loads_a_set_and_says_what_it_did(
    loader_client: TestClient,
    admin_settings: Settings,
    data_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = test_data.main(
        ["load", "--set", "low-budget", str(data_dir)],
        client=loader_client,
    )

    assert code == 0
    assert capsys.readouterr().out == "test data: low-budget is now the budget configuration\n"
    assert load_config("budget", admin_settings)["recognition_per_minute"] == 2


def test_the_command_line_unloads_and_says_what_it_did(
    loader_client: TestClient, data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    test_data.main(["load", "--set", "add-tamil", str(data_dir)], client=loader_client)
    capsys.readouterr()

    code = test_data.main(["unload", str(data_dir)], client=loader_client)

    assert code == 0
    assert "the shipped configuration is back" in capsys.readouterr().out


def test_the_command_line_fails_with_the_reason_on_standard_error(
    loader_client: TestClient, data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = test_data.main(["load", "--set", "no-such-set", str(data_dir)], client=loader_client)

    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    assert "no data set called no-such-set" in captured.err


def test_a_backend_that_cannot_be_reached_points_at_backend_url(
    data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """And the admin token appears in no message, however the attempt fails."""

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    unreachable = httpx.Client(
        base_url="http://backend.invalid:8000",
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
        transport=httpx.MockTransport(refuse),
    )

    with unreachable:
        code = test_data.main(["unload", str(data_dir)], client=unreachable)

    captured = capsys.readouterr()
    assert code == 1
    assert "cannot reach the backend at http://backend.invalid:8000" in captured.err
    assert "BACKEND_URL" in captured.err
    assert ADMIN_TOKEN not in captured.err + captured.out


def test_the_client_the_command_line_opens_uses_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BACKEND_URL", "http://staging.example:8000")
    monkeypatch.setenv("ADMIN_TOKEN", "a-token")

    with test_data._open_client() as opened:
        assert str(opened.base_url) == "http://staging.example:8000"
        assert opened.headers["Authorization"] == "Bearer a-token"


def test_without_an_admin_token_the_command_line_says_to_set_one(
    monkeypatch: pytest.MonkeyPatch, data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)

    code = test_data.main(["unload", str(data_dir)])

    assert code == 1
    assert "set ADMIN_TOKEN" in capsys.readouterr().err


def test_the_default_backend_is_the_one_a_developer_runs_locally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BACKEND_URL", raising=False)
    monkeypatch.setenv("ADMIN_TOKEN", "a-token")

    with test_data._open_client() as opened:
        assert str(opened.base_url) == test_data.DEFAULT_BACKEND_URL
