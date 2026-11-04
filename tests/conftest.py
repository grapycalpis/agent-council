import json
from copy import deepcopy

import pytest

from agent_council.backends import MockBackend
from agent_council.config import load_roles, load_settings, resource_text
from agent_council.storage import Store
from agent_council.workflow import Workflow


@pytest.fixture
def fixture():
    return json.loads(resource_text("fixtures/demo.json"))


@pytest.fixture
def roles():
    return load_roles()


@pytest.fixture
def settings():
    data = load_settings()
    data["backend"] = "mock"
    return data


@pytest.fixture
def council(tmp_path, roles, settings, fixture):
    store = Store(tmp_path / "results")
    workflow = Workflow(store)
    backend = MockBackend(deepcopy(fixture))
    directory = workflow.create(fixture["idea"], settings, roles, backend)
    return workflow, directory, backend
