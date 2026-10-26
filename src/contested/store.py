from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence

from .models import Event, Score, from_iso, iso, utcnow

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY,
  source TEXT NOT NULL,
  post_id TEXT NOT NULL,
  author TEXT NOT NULL,
  text TEXT NOT NULL,
  ts TEXT NOT NULL,
  sentiment TEXT NOT NULL,
  intensity REAL NOT NULL,
  engagement REAL NOT NULL,
  url TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  UNIQUE(source, post_id)
);
CREATE TABLE IF NOT EXISTS event_tickers (
  event_id INTEGER NOT NULL,
  ticker TEXT NOT NULL,
  PRIMARY KEY(event_id, ticker)
);
CREATE TABLE IF NOT EXISTS scores (
  ticker TEXT NOT NULL,
  ts TEXT NOT NULL,
  window_hours INTEGER NOT NULL,
  momentum INTEGER NOT NULL,
  contested INTEGER NOT NULL,
  bull_heat REAL NOT NULL,
  bear_heat REAL NOT NULL,
  n_bull INTEGER NOT NULL,
  n_bear INTEGER NOT NULL,
  PRIMARY KEY(ticker, ts, window_hours)
);
CREATE TABLE IF NOT EXISTS source_health (
  source TEXT NOT NULL,
  ts TEXT NOT NULL,
  status TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  PRIMARY KEY(source, ts)
);
"""


class Store:
    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path)
        self._conn.row_factory = sqlite3.Row

    def init(self) -> None:
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def upsert_events(self, events: Sequence[Event]) -> int:
        inserted = 0
        now_iso = iso(utcnow())
        with self._conn:
            for e in events:
                cur = self._conn.execute(
                    "INSERT OR IGNORE INTO events "
                    "(source,post_id,author,text,ts,sentiment,intensity,engagement,url,created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (e.source, e.post_id, e.author, e.text, iso(e.ts), e.sentiment,
                     e.intensity, e.engagement, e.url, now_iso),
                )
                inserted += cur.rowcount
                row = self._conn.execute(
                    "SELECT id FROM events WHERE source=? AND post_id=?",
                    (e.source, e.post_id),
                ).fetchone()
                eid = row["id"]
                for t in e.tickers:
                    self._conn.execute(
                        "INSERT OR IGNORE INTO event_tickers (event_id,ticker) VALUES (?,?)",
                        (eid, t),
                    )
        return inserted

    def _event_row(self, row) -> Event:
        tickers = tuple(row["tickers"].split("|")) if row["tickers"] else ()
        return Event(
            source=row["source"], post_id=row["post_id"], author=row["author"],
            text=row["text"], ts=from_iso(row["ts"]), sentiment=row["sentiment"],
            intensity=row["intensity"], engagement=row["engagement"],
            tickers=tickers, url=row["url"],
        )

    def events_in_window(self, now: datetime, window_hours: int, tickers: Sequence[str] | None = None) -> list:
        start = iso(now - timedelta(hours=window_hours))
        sql = (
            "SELECT e.source,e.post_id,e.author,e.text,e.ts,e.sentiment,e.intensity,"
            "e.engagement,e.url, (SELECT group_concat(t.ticker,'|') FROM event_tickers t "
            "WHERE t.event_id=e.id) AS tickers FROM events e WHERE e.ts >= ?"
        )
        params = [start]
        if tickers:
            marks = ",".join("?" for _ in tickers)
            sql += f" AND EXISTS (SELECT 1 FROM event_tickers t WHERE t.event_id=e.id AND t.ticker IN ({marks}))"
            params.extend(tickers)
        rows = self._conn.execute(sql, params).fetchall()
        return [self._event_row(r) for r in rows]

    def tickers_in_window(self, now: datetime, window_hours: int) -> list:
        start = iso(now - timedelta(hours=window_hours))
        rows = self._conn.execute(
            "SELECT DISTINCT t.ticker AS ticker FROM event_tickers t "
            "JOIN events e ON e.id=t.event_id WHERE e.ts >= ?",
            (start,),
        ).fetchall()
        return [r["ticker"] for r in rows]

    def top_tickers_by_engagement(self, now: datetime, window_hours: int, limit: int) -> list:
        start = iso(now - timedelta(hours=window_hours))
        rows = self._conn.execute(
            "SELECT t.ticker AS ticker, SUM(e.engagement) AS s FROM event_tickers t "
            "JOIN events e ON e.id=t.event_id WHERE e.ts >= ? "
            "GROUP BY t.ticker ORDER BY s DESC LIMIT ?",
            (start, limit),
        ).fetchall()
        return [r["ticker"] for r in rows]

    def save_score(self, score: Score) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO scores "
                "(ticker,ts,window_hours,momentum,contested,bull_heat,bear_heat,n_bull,n_bear) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (score.ticker, iso(score.ts), score.window_hours, score.momentum,
                 score.contested, score.bull_heat, score.bear_heat, score.n_bull, score.n_bear),
            )

    def latest_scores(self, window_hours: int) -> list:
        rows = self._conn.execute(
            "SELECT * FROM scores s WHERE s.window_hours=? AND s.ts=("
            "SELECT MAX(ts) FROM scores WHERE ticker=s.ticker AND window_hours=s.window_hours) "
            "ORDER BY momentum DESC, contested DESC",
            (window_hours,),
        ).fetchall()
        return [self._score_row(r) for r in rows]

    def score_history(self, ticker: str, window_hours: int, limit: int = 30) -> list:
        rows = self._conn.execute(
            "SELECT * FROM scores WHERE ticker=? AND window_hours=? ORDER BY ts DESC LIMIT ?",
            (ticker, window_hours, limit),
        ).fetchall()
        return [self._score_row(r) for r in reversed(rows)]

    def _score_row(self, r) -> Score:
        return Score(
            ticker=r["ticker"], ts=from_iso(r["ts"]), window_hours=r["window_hours"],
            momentum=r["momentum"], contested=r["contested"], bull_heat=r["bull_heat"],
            bear_heat=r["bear_heat"], n_bull=r["n_bull"], n_bear=r["n_bear"],
        )

    def record_health(self, source: str, ts: datetime, status: str, note: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO source_health (source,ts,status,note) VALUES (?,?,?,?)",
                (source, iso(ts), status, note),
            )

    def source_health(self) -> list:
        rows = self._conn.execute(
            "SELECT * FROM source_health h WHERE ts=("
            "SELECT MAX(ts) FROM source_health WHERE source=h.source)"
        ).fetchall()
        return [(r["source"], from_iso(r["ts"]), r["status"], r["note"]) for r in rows]
