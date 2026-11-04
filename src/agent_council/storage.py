"""每次評估獨立目錄、不可覆寫封存及原子狀態更新。"""

import json
import os
import re
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .domain import CouncilError, Json


def timestamp() -> str:
    return datetime.now(UTC).isoformat()


def read_json(path: Path) -> Json:
    return json.loads(path.read_text(encoding="utf-8"))


def encode(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_once(path: Path, data: object, *, text: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".artifact-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(str(data) if text else encode(data))
            stream.flush()
            os.fsync(stream.fileno())
        # link 原子建立且目標存在時失敗，避免半寫入檔案破壞復原能力。
        os.link(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def atomic_json(path: Path, data: object) -> None:
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".state-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(encode(data))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


class Store:
    def __init__(self, root: Path):
        self.root = root

    def locate(self, evaluation_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", evaluation_id):
            raise CouncilError("評估 ID 格式錯誤")
        path = self.root / evaluation_id
        if not path.is_dir() or path.is_symlink():
            raise CouncilError("找不到評估紀錄")
        return path

    def create(self, idea: Json, snapshot: Json) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        eid = datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "_" + uuid4().hex[:12]
        path = self.root / eid
        path.mkdir(exist_ok=False)
        write_once(path / "idea.json", idea)
        write_once(path / "snapshot.json", snapshot)
        atomic_json(
            path / "state.json",
            {
                "evaluation_id": eid,
                "created_at": timestamp(),
                "status": "running",
                "phase_index": 0,
                "records": {},
                "phase_log": [],
            },
        )
        return path

    @contextmanager
    def lock(self, path: Path) -> Iterator[None]:
        # 程序崩潰時 OS 會釋放鎖；不刪除 inode，避免重建鎖造成競態。
        import fcntl

        with (path / ".lock").open("a") as stream:
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise CouncilError("此評估正由另一個程序更新") from exc
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def summaries(self) -> list[Json]:
        if not self.root.exists():
            return []
        summaries = []
        for path in sorted(self.root.iterdir(), reverse=True):
            if path.is_dir() and not path.is_symlink() and (path / "state.json").exists():
                state = read_json(path / "state.json")
                summaries.append(
                    {
                        "evaluation_id": state["evaluation_id"],
                        "status": state["status"],
                        "title": read_json(path / "idea.json")["title"],
                        "execution_kind": read_json(path / "snapshot.json")["backend"][
                            "execution_kind"
                        ],
                    }
                )
        return summaries
