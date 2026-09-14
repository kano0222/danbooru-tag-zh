from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import webbrowser
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .models import CATEGORY_NAMES
from .review_ui import REVIEW_HTML

CATEGORY_IDS = {name: category for category, name in CATEGORY_NAMES.items() if category != 1}
REVIEWABLE_STATUSES = {"no_candidate", "single_candidate", "multiple_candidates"}
DECISION_ACTIONS = {"accept", "skip", "no_suitable"}
MAX_TRANSLATION_LENGTH = 80
MAX_REQUEST_BYTES = 64 * 1024


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class ReviewStore:
    def __init__(self, database: Path, decisions_path: Path) -> None:
        if not database.is_file():
            raise ValueError(f"candidate database does not exist: {database}")
        self.database = database.resolve()
        self.decisions_path = decisions_path.resolve()
        self._lock = threading.RLock()
        self._decisions = self._load_decisions()
        self._undo_state: tuple[str, dict[str, Any] | None] | None = None

    def _load_decisions(self) -> dict[str, dict[str, Any]]:
        if not self.decisions_path.exists():
            return {}
        raw = json.loads(self.decisions_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("schema_version") != 1:
            raise ValueError("manual translation file has an unsupported schema")
        decisions = raw.get("decisions")
        if not isinstance(decisions, dict):
            raise ValueError("manual translation decisions must be an object")
        return {str(tag): value for tag, value in decisions.items() if isinstance(value, dict)}

    def _save(self) -> None:
        self.decisions_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": 1, "decisions": dict(sorted(self._decisions.items()))}
        data = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=self.decisions_path.parent, delete=False
        ) as handle:
            handle.write(data)
            temporary = Path(handle.name)
        temporary.replace(self.decisions_path)

    def item(
        self,
        *,
        offset: int,
        category: str,
        candidate_status: str,
        review_status: str,
        query: str,
    ) -> dict[str, Any]:
        if category not in {"all", *CATEGORY_IDS}:
            raise ValueError("invalid category filter")
        if candidate_status not in {
            "no_candidate",
            "single_candidate",
            "multiple_candidates",
            "all",
        }:
            raise ValueError("invalid candidate-status filter")
        if review_status not in {"pending", "all", *DECISION_ACTIONS}:
            raise ValueError("invalid review-status filter")
        clauses = [
            "(status IN ('single_candidate', 'multiple_candidates') OR "
            "(status = 'no_candidate' AND wikipedia_references != '[]'))"
        ]
        parameters: list[object] = []
        if category != "all":
            clauses.append("category = ?")
            parameters.append(CATEGORY_IDS[category])
        if candidate_status != "all":
            clauses.append("status = ?")
            parameters.append(candidate_status)
        if query:
            clauses.append("tag_name LIKE ? ESCAPE '\\'")
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            parameters.append(f"%{escaped}%")
        sql = (
            "SELECT tag_id, tag_name, category, post_count, status, source_url, "  # noqa: S608
            "inferred_translation, inference_reason, inference_source_url, wikipedia_references "
            f"FROM candidate_groups WHERE {' AND '.join(clauses)} "
            "ORDER BY post_count DESC, tag_name"
        )
        connection = sqlite3.connect(f"{self.database.as_uri()}?mode=ro", uri=True)
        try:
            has_reference_aliases = any(
                str(column[1]) == "reference_aliases"
                for column in connection.execute("PRAGMA table_info(candidate_groups)")
            )
            rows = connection.execute(sql, parameters).fetchall()
            with self._lock:
                filtered = [
                    row for row in rows if self._matches_review(str(row[1]), row[6], review_status)
                ]
                total = len(filtered)
                if total == 0:
                    return {
                        "offset": 0,
                        "total": 0,
                        "can_undo": self._undo_state is not None,
                        "item": None,
                    }
                selected_offset = max(0, min(offset, total - 1))
                row = filtered[selected_offset]
                candidates = [
                    str(candidate[0])
                    for candidate in connection.execute(
                        "SELECT value FROM translation_candidates WHERE tag_id = ? ORDER BY rank",
                        (row[0],),
                    )
                ]
                tag_name = str(row[1])
                aliases: list[str] = []
                if has_reference_aliases:
                    raw_aliases = connection.execute(
                        "SELECT reference_aliases FROM candidate_groups WHERE tag_id = ?",
                        (row[0],),
                    ).fetchone()[0]
                    parsed_aliases = json.loads(str(raw_aliases))
                    if isinstance(parsed_aliases, list):
                        aliases = [str(alias) for alias in parsed_aliases if isinstance(alias, str)]
                decision = self._decisions.get(tag_name)
                if decision is None and row[6] is not None:
                    reason = str(row[7])
                    decision = {
                        "action": "accept",
                        "translation": str(row[6]),
                        "source": (
                            "wikipedia_inferred"
                            if reason in {"wikipedia_zh_title", "danbooru_wiki_and_wikipedia"}
                            else "wiki_inferred"
                        ),
                        "reason": reason,
                        "source_url": str(row[8]) if row[8] is not None else str(row[5]),
                    }
                return {
                    "offset": selected_offset,
                    "total": total,
                    "can_undo": self._undo_state is not None,
                    "item": {
                        "tag": tag_name,
                        "category": CATEGORY_NAMES[int(row[2])],
                        "post_count": int(row[3]),
                        "candidate_status": str(row[4]),
                        "source_url": str(row[5]),
                        "candidates": candidates,
                        "reference_aliases": aliases,
                        "wikipedia_references": json.loads(str(row[9])),
                        "decision": decision,
                    },
                }
        finally:
            connection.close()

    def _matches_review(self, tag: str, inferred: object, review_status: str) -> bool:
        decision = self._decisions.get(tag)
        action = decision.get("action") if decision is not None else None
        if action is None and inferred is not None:
            action = "accept"
        if review_status == "all":
            return True
        if review_status == "pending":
            return action is None
        return action == review_status

    def decide(self, raw: object) -> dict[str, Any]:
        if not isinstance(raw, dict):
            raise ValueError("decision must be an object")
        tag = raw.get("tag")
        action = raw.get("action")
        if not isinstance(tag, str) or not tag:
            raise ValueError("decision tag is required")
        if action == "clear":
            with self._lock:
                previous = self._decisions.get(tag)
                if previous is None:
                    return {"ok": True}
                self._undo_state = (tag, previous.copy())
                self._decisions.pop(tag, None)
                self._save()
            return {"ok": True}
        if action not in DECISION_ACTIONS:
            raise ValueError("invalid decision action")
        group, candidates = self._group(tag)
        decision: dict[str, Any] = {
            "action": action,
            "category": group[0],
            "post_count": group[1],
            "wiki_page_id": group[2],
            "source_url": group[3],
            "reviewed_at": _now(),
        }
        if action == "accept":
            translation = raw.get("translation")
            if not isinstance(translation, str):
                raise ValueError("accepted decision requires a translation")
            translation = translation.strip()
            if not translation or len(translation) > MAX_TRANSLATION_LENGTH:
                raise ValueError("translation length is invalid")
            if any(ord(char) < 32 or ord(char) == 127 for char in translation):
                raise ValueError("translation contains a control character")
            decision["translation"] = translation
            if translation.replace("_", " ").casefold() == tag.replace("_", " ").casefold():
                decision["source"] = "original_term"
            else:
                decision["source"] = "wiki_other_name" if translation in candidates else "manual"
        with self._lock:
            previous = self._decisions.get(tag)
            self._undo_state = (tag, previous.copy() if previous is not None else None)
            self._decisions[tag] = decision
            self._save()
        return {"ok": True, "decision": decision}

    def undo(self) -> dict[str, Any]:
        with self._lock:
            if self._undo_state is None:
                raise ValueError("there is no decision to undo")
            tag, previous = self._undo_state
            if previous is None:
                self._decisions.pop(tag, None)
            else:
                self._decisions[tag] = previous
            self._undo_state = None
            self._save()
        return {"ok": True, "tag": tag}

    def _group(self, tag: str) -> tuple[tuple[str, int, int | None, str], list[str]]:
        connection = sqlite3.connect(f"{self.database.as_uri()}?mode=ro", uri=True)
        try:
            row = connection.execute(
                "SELECT category, post_count, wiki_page_id, source_url, status "
                "FROM candidate_groups WHERE tag_name = ?",
                (tag,),
            ).fetchone()
            if row is None or row[4] not in REVIEWABLE_STATUSES:
                raise ValueError("tag does not have reviewable candidates")
            candidates = [
                str(value[0])
                for value in connection.execute(
                    "SELECT value FROM translation_candidates "
                    "WHERE tag_id = (SELECT tag_id FROM candidate_groups WHERE tag_name = ?) "
                    "ORDER BY rank",
                    (tag,),
                )
            ]
            return (
                (CATEGORY_NAMES[int(row[0])], int(row[1]), row[2], str(row[3])),
                candidates,
            )
        finally:
            connection.close()

    def stats(self) -> dict[str, Any]:
        with self._lock:
            decisions = list(self._decisions.values())
        counts = {action: 0 for action in sorted(DECISION_ACTIONS)}
        for decision in decisions:
            action = decision.get("action")
            if action in counts:
                counts[action] += 1
        return {"reviewed": sum(counts.values()), "by_action": counts}


class ReviewHandler(BaseHTTPRequestHandler):
    store: ReviewStore

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/":
                self._send(HTTPStatus.OK, REVIEW_HTML.encode(), "text/html; charset=utf-8")
                return
            if parsed.path == "/api/item":
                query = parse_qs(parsed.query)
                result = self.store.item(
                    offset=int(query.get("offset", ["0"])[0]),
                    category=query.get("category", ["all"])[0],
                    candidate_status=query.get("candidate_status", ["multiple_candidates"])[0],
                    review_status=query.get("review_status", ["pending"])[0],
                    query=query.get("q", [""])[0].strip()[:100],
                )
                self._json(HTTPStatus.OK, result)
                return
            if parsed.path == "/api/stats":
                self._json(HTTPStatus.OK, self.store.stats())
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/undo":
            try:
                self._json(HTTPStatus.OK, self.store.undo())
            except (ValueError, OSError) as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        if path != "/api/decision":
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_REQUEST_BYTES:
                raise ValueError("invalid request size")
            payload = json.loads(self.rfile.read(length))
            self._json(HTTPStatus.OK, self.store.decide(payload))
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def _json(self, status: HTTPStatus, value: object) -> None:
        self._send(
            status,
            json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode(),
            "application/json; charset=utf-8",
        )

    def _send(self, status: HTTPStatus, data: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:
        return


def run_review_server(
    database: Path,
    decisions: Path,
    *,
    host: str,
    port: int,
    open_browser: bool,
) -> None:
    store = ReviewStore(database, decisions)

    ReviewHandler.store = store
    server = ThreadingHTTPServer((host, port), ReviewHandler)
    url = f"http://{host}:{server.server_port}/"
    print(f"Review UI: {url}")
    print("Press Ctrl+C to stop.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
