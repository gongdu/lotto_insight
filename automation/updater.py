"""Incremental updater for LottoInsight.

Sources are the official dhlottery pages/endpoints. The updater is defensive:
- a draw is written only after structural validation;
- winning-store rows replace a whole round only after count validation (Lotto 1/2 rank);
- parser/fetch failures are logged and existing data is left untouched.

The current dhlottery site changes markup occasionally, so several JSON endpoint candidates
and HTML fallbacks are tried. Keep parser fixture tests when adapting to future markup.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlencode

import httpx
from bs4 import BeautifulSoup, Tag

DB = Path(os.getenv("LOTTO_DB", Path(__file__).parent.parent / "data/seed/lotto_app.db"))
BASE = "https://www.dhlottery.co.kr"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 LottoInsight/2.0",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
    "Accept": "application/json,text/html,application/xhtml+xml,*/*;q=0.8",
}
TIMEOUT = 20.0

KST = ZoneInfo("Asia/Seoul")

def expected_latest_lotto(now: datetime | None = None) -> int:
    now = now or datetime.now(KST)
    first = datetime(2002, 12, 7, 20, 35, tzinfo=KST)
    if now < first:
        return 0
    return int((now - first) // timedelta(days=7)) + 1

def expected_latest_pension(now: datetime | None = None) -> int:
    now = now or datetime.now(KST)
    first = datetime(2020, 5, 7, 19, 5, tzinfo=KST)
    if now < first:
        return 0
    return int((now - first) // timedelta(days=7)) + 1



def ensure_schema(c: sqlite3.Connection) -> None:
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS sync_state(dataset TEXT PRIMARY KEY, latest_round INTEGER NOT NULL DEFAULT 0, updated_at TEXT);
        CREATE TABLE IF NOT EXISTS update_log(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          dataset TEXT NOT NULL, round INTEGER, status TEXT NOT NULL, message TEXT,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_lws_round_rank ON lotto_winning_stores(round,rank);
        CREATE INDEX IF NOT EXISTS idx_pension_round ON pension_results(round);
        CREATE INDEX IF NOT EXISTS idx_pws_round ON pension_winning_stores(lottery_type,round);
        """
    )
    seeds = {
        "lotto": c.execute("SELECT COALESCE(MAX(round),0) FROM lotto_draws").fetchone()[0],
        "lotto_stores": c.execute("SELECT COALESCE(MAX(round),0) FROM lotto_winning_stores").fetchone()[0],
        "pension": c.execute("SELECT COALESCE(MAX(round),0) FROM pension_results").fetchone()[0],
        "pension_stores": c.execute(
            "SELECT COALESCE(MAX(round),0) FROM pension_winning_stores WHERE lottery_type='PensionLottery720'"
        ).fetchone()[0],
    }
    for dataset, latest in seeds.items():
        c.execute(
            """INSERT INTO sync_state(dataset,latest_round,updated_at) VALUES(?,?,CURRENT_TIMESTAMP)
               ON CONFLICT(dataset) DO NOTHING""",
            (dataset, latest),
        )
    c.commit()


def log(c: sqlite3.Connection, dataset: str, round_no: int | None, status: str, message: str) -> None:
    c.execute(
        "INSERT INTO update_log(dataset,round,status,message) VALUES(?,?,?,?)",
        (dataset, round_no, status, message[:2000]),
    )


def state(c: sqlite3.Connection, dataset: str) -> int:
    row = c.execute("SELECT latest_round FROM sync_state WHERE dataset=?", (dataset,)).fetchone()
    return int(row[0]) if row else 0


def set_state(c: sqlite3.Connection, dataset: str, round_no: int) -> None:
    c.execute(
        """INSERT INTO sync_state(dataset,latest_round,updated_at) VALUES(?,?,CURRENT_TIMESTAMP)
           ON CONFLICT(dataset) DO UPDATE SET latest_round=excluded.latest_round,updated_at=CURRENT_TIMESTAMP""",
        (dataset, round_no),
    )


def _request(url: str) -> httpx.Response:
    r = httpx.get(url, headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)
    r.raise_for_status()
    return r


def _walk(obj: Any) -> Iterable[Any]:
    yield obj
    if isinstance(obj, dict):
        for value in obj.values():
            yield from _walk(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _walk(value)


def _as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    s = re.sub(r"[^0-9-]", "", str(value))
    try:
        return int(s) if s not in {"", "-"} else None
    except ValueError:
        return None


def _as_float(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _first(d: dict[str, Any], *keys: str) -> Any:
    lower = {str(k).lower(): v for k, v in d.items()}
    for key in keys:
        if key in d:
            return d[key]
        if key.lower() in lower:
            return lower[key.lower()]
    return None


def _round_from_dict(d: dict[str, Any]) -> int | None:
    for key, value in d.items():
        lk = str(key).lower()
        if "epsd" in lk or lk in {"round", "drawno", "drwno"}:
            n = _as_int(value)
            if n is not None:
                return n
    return None


def _find_round(obj: Any, round_no: int) -> dict[str, Any] | None:
    for node in _walk(obj):
        if isinstance(node, dict) and _round_from_dict(node) == round_no:
            return node
    return None


def _date(value: Any) -> str:
    s = str(value or "")
    patterns = [
        r"(20\d{2})\D{0,3}(\d{1,2})\D{0,3}(\d{1,2})",
        r"(20\d{2})(\d{2})(\d{2})",
    ]
    for p in patterns:
        m = re.search(p, s)
        if m:
            y, mo, d = map(int, m.groups())
            if 1 <= mo <= 12 and 1 <= d <= 31:
                return f"{y:04d}-{mo:02d}-{d:02d}"
    return ""


# ---------------- Lotto 6/45 result ----------------

def _mapped_lotto(x: dict[str, Any]) -> dict[str, Any]:
    return {
        "round": int(x["ltEpsd"]),
        "date": _date(x.get("ltRflYmd")),
        "numbers": [int(x[f"tm{i}WnNo"]) for i in range(1, 7)],
        "bonus": int(x["bnsWnNo"]),
        "first_prize": _as_int(x.get("rnk1WnAmt")),
        "first_winners": _as_int(x.get("rnk1WnNope")),
        "total_sales": _as_int(x.get("rlvtEpsdSumNtslAmt")),
        "auto": _as_int(x.get("winType1")),
        "manual": _as_int(x.get("winType2")),
        "half": _as_int(x.get("winType3")),
        "second_prize": _as_int(x.get("rnk2WnAmt")),
        "second_winners": _as_int(x.get("rnk2WnNope")),
        "third_prize": _as_int(x.get("rnk3WnAmt")),
        "third_winners": _as_int(x.get("rnk3WnNope")),
        "fourth_prize": _as_int(x.get("rnk4WnAmt")),
        "fourth_winners": _as_int(x.get("rnk4WnNope")),
        "fifth_prize": _as_int(x.get("rnk5WnAmt")),
        "fifth_winners": _as_int(x.get("rnk5WnNope")),
    }


def _valid_lotto(d: dict[str, Any]) -> bool:
    nums = list(d.get("numbers") or [])
    bonus = d.get("bonus")
    return (
        len(nums) == 6
        and len(set(nums)) == 6
        and all(isinstance(n, int) and 1 <= n <= 45 for n in nums)
        and isinstance(bonus, int)
        and 1 <= bonus <= 45
        and bonus not in nums
    )


def fetch_lotto(round_no: int) -> dict[str, Any]:
    ts = int(time.time() * 1000)
    urls = [
        f"{BASE}/lt645/selectPstLt645Info.do?srchLtEpsd={round_no}&_={ts}",
        f"{BASE}/lt645/selectPstLt645InfoNew.do?srchDir=center&srchLtEpsd={round_no}",
    ]
    errors: list[str] = []
    for url in urls:
        try:
            r = _request(url)
            payload = r.json()
            found = _find_round(payload, round_no)
            if found and all(k in found for k in ["ltEpsd", "tm1WnNo", "tm6WnNo", "bnsWnNo"]):
                d = _mapped_lotto(found)
                if _valid_lotto(d):
                    return d
        except Exception as e:  # endpoint may disappear; try next source
            errors.append(f"{url}: {e}")

    try:
        r = _request(f"{BASE}/lt645/result?ltEpsd={round_no}")
        soup = BeautifulSoup(r.text, "html.parser")
        text = " ".join(soup.stripped_strings)
        m = re.search(
            r"(?:당첨번호|winning[^\d]{0,20})(\d{1,2})\D+(\d{1,2})\D+(\d{1,2})\D+(\d{1,2})\D+(\d{1,2})\D+(\d{1,2}).{0,120}(?:보너스|bonus)\D+(\d{1,2})",
            text,
            re.I | re.S,
        )
        if m:
            values = list(map(int, m.groups()))
            d = {"round": round_no, "date": _date(text), "numbers": values[:6], "bonus": values[6]}
            if _valid_lotto(d):
                return d
    except Exception as e:
        errors.append(f"html: {e}")
    raise RuntimeError(" | ".join(errors) or "official lotto result could not be parsed")


def upsert_lotto(c: sqlite3.Connection, d: dict[str, Any]) -> None:
    c.execute(
        """INSERT INTO lotto_draws(
             round,draw_date,n1,n2,n3,n4,n5,n6,bonus,first_prize,first_winners,total_sales,
             first_auto,first_manual,first_half_auto,second_prize,second_winners,third_prize,third_winners,
             fourth_prize,fourth_winners,fifth_prize,fifth_winners)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(round) DO UPDATE SET
             draw_date=excluded.draw_date,n1=excluded.n1,n2=excluded.n2,n3=excluded.n3,n4=excluded.n4,n5=excluded.n5,n6=excluded.n6,bonus=excluded.bonus,
             first_prize=excluded.first_prize,first_winners=excluded.first_winners,total_sales=excluded.total_sales,
             first_auto=excluded.first_auto,first_manual=excluded.first_manual,first_half_auto=excluded.first_half_auto,
             second_prize=excluded.second_prize,second_winners=excluded.second_winners,third_prize=excluded.third_prize,third_winners=excluded.third_winners,
             fourth_prize=excluded.fourth_prize,fourth_winners=excluded.fourth_winners,fifth_prize=excluded.fifth_prize,fifth_winners=excluded.fifth_winners,
             updated_at=CURRENT_TIMESTAMP""",
        (
            d["round"], d.get("date", ""), *d["numbers"], d["bonus"],
            d.get("first_prize"), d.get("first_winners"), d.get("total_sales"), d.get("auto"), d.get("manual"), d.get("half"),
            d.get("second_prize"), d.get("second_winners"), d.get("third_prize"), d.get("third_winners"),
            d.get("fourth_prize"), d.get("fourth_winners"), d.get("fifth_prize"), d.get("fifth_winners"),
        ),
    )


# ---------------- Winning stores ----------------

STORE_NAME_KEYS = ("shpNm", "storeName", "storeNm", "name", "slrNm")
STORE_ID_KEYS = ("ltShpId", "storeId", "shpId", "slrId")
STORE_ADDRESS_KEYS = ("shpAddr", "roadAddress", "roadAddr", "address", "bplcLctnAddr")
STORE_PHONE_KEYS = ("shpTelno", "phone", "tel", "telno")
STORE_RANK_KEYS = ("wnShpRnk", "wnRnkVl", "rank", "winningRank", "rnk")


def _region_from_address(address: str) -> str:
    if not address:
        return ""
    first = address.split()[0]
    replacements = {
        "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천",
        "광주광역시": "광주", "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종",
        "경기도": "경기", "강원특별자치도": "강원", "충청북도": "충북", "충청남도": "충남",
        "전북특별자치도": "전북", "전라북도": "전북", "전라남도": "전남", "경상북도": "경북",
        "경상남도": "경남", "제주특별자치도": "제주",
    }
    return replacements.get(first, first)


def _map_store_dict(d: dict[str, Any], round_no: int, forced_rank: int | None = None) -> dict[str, Any] | None:
    name = _first(d, *STORE_NAME_KEYS)
    if not name or len(str(name).strip()) < 2:
        return None
    rd = _round_from_dict(d)
    if rd is not None and rd != round_no:
        return None
    address = str(_first(d, *STORE_ADDRESS_KEYS) or "").strip()
    rank = forced_rank or _as_int(_first(d, *STORE_RANK_KEYS))
    return {
        "round": round_no,
        "rank": rank,
        "store_id": str(_first(d, *STORE_ID_KEYS) or "").strip() or None,
        "name": str(name).strip(),
        "phone": str(_first(d, *STORE_PHONE_KEYS) or "").strip() or None,
        "region": str(_first(d, "region", "sidoNm", "ctpvNm") or _region_from_address(address)).strip(),
        "address": address,
        "auto_possible": str(_first(d, "atmtPsvYn", "autoPossible", "atmtPsvYnTxt") or "").strip() or None,
        "latitude": _as_float(_first(d, "shpLat", "latitude", "lat")),
        "longitude": _as_float(_first(d, "shpLot", "longitude", "lng", "lon")),
        "winning_rank": _as_int(_first(d, "wnRnkVl", "winningRank", "rank")),
        "winning_store_rank": _as_int(_first(d, "wnShpRnk", "winningStoreRank")),
    }


def _stores_from_json(payload: Any, round_no: int, forced_rank: int | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for node in _walk(payload):
        if isinstance(node, dict):
            keys = {str(k).lower() for k in node.keys()}
            if any(k.lower() in keys for k in STORE_NAME_KEYS):
                mapped = _map_store_dict(node, round_no, forced_rank)
                if mapped:
                    out.append(mapped)
    return out


def _tag_full_text(tag: Tag) -> str:
    bits = list(tag.stripped_strings)
    for _, value in tag.attrs.items():
        vals = value if isinstance(value, list) else [value]
        bits.extend(str(v) for v in vals if v is not None)
    return " ".join(bits)


def _looks_address(text: str) -> bool:
    return bool(re.search(r"(?:특별시|광역시|특별자치|[가-힣]+도)\s+.*(?:시|군|구|읍|면|동|로|길)", text))


def _stores_from_html(html: str, round_no: int, forced_rank: int | None = None) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict[str, Any]] = []

    # Embedded JSON is common on SPA/server-hybrid pages.
    for script in soup.find_all("script"):
        raw = script.string or script.get_text(" ", strip=True)
        if not raw or "shp" not in raw.lower():
            continue
        candidates = [raw.strip()]
        m = re.search(r"(?:=|:)\s*(\{.*\}|\[.*\])\s*;?\s*$", raw, re.S)
        if m:
            candidates.append(m.group(1))
        for candidate in candidates:
            try:
                out.extend(_stores_from_json(json.loads(candidate), round_no, forced_rank))
            except Exception:
                pass

    # Table fallback. Only accept rows that carry a rank, unless caller used a rank-filtered URL.
    for tr in soup.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if not cells:
            continue
        texts = [_tag_full_text(cell).strip() for cell in cells]
        joined = " | ".join(texts)
        rank_m = re.search(r"\b([12])\s*등\b", joined)
        rank = forced_rank or (int(rank_m.group(1)) if rank_m else None)
        if rank is None:
            continue
        address = max((t for t in texts if _looks_address(t)), key=len, default="")
        if not address:
            continue
        phone_m = re.search(r"0\d{1,2}-\d{3,4}-\d{4}", joined)
        excluded = {address}
        if phone_m:
            excluded.add(phone_m.group(0))
        name_candidates = [
            t for t in texts
            if t not in excluded
            and not re.fullmatch(r"\d+", t)
            and not re.search(r"^[12]\s*등$", t)
            and not _looks_address(t)
            and len(t) >= 2
            and "자동" not in t
        ]
        if not name_candidates:
            continue
        name = min(name_candidates, key=len)
        out.append({
            "round": round_no, "rank": rank, "store_id": None, "name": name,
            "phone": phone_m.group(0) if phone_m else None,
            "region": _region_from_address(address), "address": address,
            "auto_possible": "Y" if "자동" in joined else None,
            "latitude": None, "longitude": None, "winning_rank": rank, "winning_store_rank": None,
        })
    return out


def _dedupe_exact(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Keep legitimate repeated winning tickets. Only drop byte-for-byte parser duplicates from the same response.
    seen: set[tuple[Any, ...]] = set()
    out = []
    for row in rows:
        key = tuple(row.get(k) for k in ["round", "rank", "store_id", "name", "address", "phone", "winning_store_rank"])
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _validate_lotto_store_counts(rows: list[dict[str, Any]], first: int | None, second: int | None) -> bool:
    if not rows:
        return False
    counts = {1: 0, 2: 0}
    for row in rows:
        rank = _as_int(row.get("rank"))
        if rank in counts:
            counts[rank] += 1
        else:
            return False
    if first is not None and counts[1] != first:
        return False
    if second is not None and counts[2] != second:
        return False
    return True


def fetch_winning_stores(
    round_no: int,
    product: str,
    expected_first: int | None = None,
    expected_second: int | None = None,
) -> list[dict[str, Any]]:
    """Fetch official winning stores.

    product: 'lt645' or 'pt720'. Lotto is accepted only when 1/2-rank row counts match
    the draw's official winner counts. This prevents placeholder/partially rendered pages
    from replacing good data.
    """
    errors: list[str] = []
    base_params = {"ltEpsd": round_no, "ltGds": product}
    urls: list[tuple[str, int | None]] = []
    endpoint_names = [
        "selectWnPrchSplc.do", "selectWnPrchSplcList.do", "selectWnprchSplcList.do",
        "selectWnPrchSplcInfo.do", "selectWnShpList.do",
    ]
    for endpoint in endpoint_names:
        urls.append((f"{BASE}/wnprchsplcsrch/{endpoint}?{urlencode(base_params)}", None))
    urls.append((f"{BASE}/wnprchsplcsrch/home?{urlencode(base_params)}", None))

    # Rank-filter variants are attempted for Lotto. If a parameter is ignored, count validation rejects it.
    if product == "lt645":
        for rank in (1, 2):
            for key in ("wnRnk", "rank", "wnShpRnk"):
                params = dict(base_params)
                params[key] = rank
                urls.append((f"{BASE}/wnprchsplcsrch/home?{urlencode(params)}", rank))

    best: list[dict[str, Any]] = []
    per_rank: dict[int, list[dict[str, Any]]] = {1: [], 2: []}
    for url, forced_rank in urls:
        try:
            r = _request(url)
            rows: list[dict[str, Any]] = []
            try:
                rows.extend(_stores_from_json(r.json(), round_no, forced_rank))
            except Exception:
                pass
            if not rows:
                rows.extend(_stores_from_html(r.text, round_no, forced_rank))
            if not rows:
                continue
            if product == "lt645":
                if forced_rank in (1, 2):
                    if len(rows) > len(per_rank[forced_rank]):
                        per_rank[forced_rank] = rows
                    merged = per_rank[1] + per_rank[2]
                    if _validate_lotto_store_counts(merged, expected_first, expected_second):
                        return merged
                elif _validate_lotto_store_counts(rows, expected_first, expected_second):
                    return rows
            else:
                # For Pension720 the official page only lists eligible winning stores; no exact
                # count is exposed in our normalized draw table, so non-empty validated rows suffice.
                best = rows if len(rows) > len(best) else best
        except Exception as e:
            errors.append(f"{url}: {e}")
    if product == "pt720" and best:
        return best
    raise RuntimeError("winning stores could not be validated: " + " | ".join(errors[-5:]))


def replace_lotto_stores(c: sqlite3.Connection, round_no: int, rows: list[dict[str, Any]]) -> None:
    c.execute("DELETE FROM lotto_winning_stores WHERE round=?", (round_no,))
    c.executemany(
        """INSERT INTO lotto_winning_stores(
             round,rank,store_id,name,phone,region,address,auto_possible,latitude,longitude)
           VALUES(?,?,?,?,?,?,?,?,?,?)""",
        [(
            round_no, int(r["rank"]), r.get("store_id"), r["name"], r.get("phone"), r.get("region"),
            r.get("address"), r.get("auto_possible"), r.get("latitude"), r.get("longitude")
        ) for r in rows],
    )


def replace_pension_stores(c: sqlite3.Connection, round_no: int, rows: list[dict[str, Any]]) -> None:
    c.execute("DELETE FROM pension_winning_stores WHERE lottery_type='PensionLottery720' AND round=?", (round_no,))
    c.executemany(
        """INSERT INTO pension_winning_stores(
             lottery_type,round,store_id,name,address,phone,region,latitude,longitude,winning_rank,winning_store_rank)
           VALUES('PensionLottery720',?,?,?,?,?,?,?,?,?,?)""",
        [(
            round_no, r.get("store_id"), r["name"], r.get("address"), r.get("phone"), r.get("region"),
            r.get("latitude"), r.get("longitude"), r.get("winning_rank") or r.get("rank"), r.get("winning_store_rank")
        ) for r in rows],
    )


# ---------------- Pension Lottery 720+ ----------------


def _single_digits(tag: Tag) -> list[int]:
    tokens: list[str] = []
    for s in tag.stripped_strings:
        tokens.append(str(s).strip())
    for node in tag.find_all(True):
        for key in ("alt", "title", "data-num", "data-number", "value"):
            if node.has_attr(key):
                tokens.append(str(node.get(key)).strip())
        src = str(node.get("src") or "")
        m = re.search(r"(?:^|[/_-])([0-9])(?:\.[a-z]+|[/_-]|$)", src, re.I)
        if m:
            tokens.append(m.group(1))
    return [int(t) for t in tokens if re.fullmatch(r"[0-9]", t)]


def _pension_rows_from_json(payload: Any, round_no: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for node in _walk(payload):
        if not isinstance(node, dict):
            continue
        rd = _round_from_dict(node)
        if rd not in (None, round_no):
            continue
        rank = _as_int(_first(node, "rank", "wnRnkVl", "rnk", "rankCd"))
        number = _first(node, "rankNo", "wnNo", "przNo", "wnNum", "winningNo", "ptWnNo")
        if rank is None or number is None:
            continue
        number_s = re.sub(r"\D", "", str(number))
        if not number_s:
            continue
        rank_class = str(_first(node, "rankClass", "wnGroup", "jo", "groupNo") or "")
        rows.append({
            "round": round_no,
            "rank": rank,
            "rank_class": re.sub(r"\D", "", rank_class),
            "rank_no": number_s,
            "prize_amount": _as_int(_first(node, "rankAmt", "wnAmt", "prizeAmount", "wnPrize")),
            "winner_count": _as_int(_first(node, "winningCnt", "wnNope", "winnerCount", "wnCnt")),
            "draw_date": _date(_first(node, "drawDate", "psltRflYmd", "ltRflYmd", "date")),
        })
    # Prefer a complete explicit 8-row payload.
    unique = {(r["rank"], r["rank_class"], r["rank_no"]): r for r in rows}
    return list(unique.values())


def _infer_pension_date(round_no: int) -> str:
    return (date(2020, 5, 7) + timedelta(days=(round_no - 1) * 7)).isoformat()


def _build_pension_rows(round_no: int, group: int, first_no: str, bonus_no: str, draw_date: str) -> list[dict[str, Any]]:
    if group not in range(1, 6) or not re.fullmatch(r"\d{6}", first_no) or not re.fullmatch(r"\d{6}", bonus_no):
        raise ValueError("invalid Pension720 winning number")
    prizes = {1: 1_680_000_000, 2: 120_000_000, 3: 1_000_000, 4: 100_000, 5: 50_000, 6: 5_000, 7: 1_000, 21: 120_000_000}
    suffix_len = {1: 6, 2: 6, 3: 5, 4: 4, 5: 3, 6: 2, 7: 1}
    out = []
    for rank in range(1, 8):
        out.append({
            "round": round_no,
            "rank": rank,
            "rank_class": str(group) if rank == 1 else "",
            "rank_no": first_no[-suffix_len[rank]:],
            "prize_amount": prizes[rank],
            "winner_count": None,
            "draw_date": draw_date,
        })
    out.append({
        "round": round_no, "rank": 21, "rank_class": "", "rank_no": bonus_no,
        "prize_amount": prizes[21], "winner_count": None, "draw_date": draw_date,
    })
    return out


def parse_pension_html(html: str, round_no: int) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    draw_date = _date(" ".join(soup.stripped_strings)) or _infer_pension_date(round_no)
    first_digits: list[int] | None = None
    bonus_digits: list[int] | None = None

    for tr in soup.find_all("tr"):
        txt = " ".join(tr.stripped_strings)
        digits = _single_digits(tr)
        if first_digits is None and re.search(r"(^|\s)1\s*등", txt) and len(digits) >= 7:
            first_digits = digits[:7]
        if bonus_digits is None and "보너스" in txt and len(digits) >= 6:
            bonus_digits = digits[:6]

    # Some responsive layouts use div/li cards rather than table rows.
    if first_digits is None or bonus_digits is None:
        for tag in soup.find_all(["div", "li", "section", "article"]):
            txt = " ".join(tag.stripped_strings)
            if len(txt) > 1200:
                continue
            digits = _single_digits(tag)
            if first_digits is None and re.search(r"(^|\s)1\s*등", txt) and len(digits) >= 7:
                first_digits = digits[:7]
            if bonus_digits is None and "보너스" in txt and len(digits) >= 6:
                bonus_digits = digits[:6]
            if first_digits is not None and bonus_digits is not None:
                break

    # Script fallback for compact serialized strings: 1st group + six digits and bonus six digits.
    if first_digits is None:
        raw = "\n".join((s.string or "") for s in soup.find_all("script"))
        m = re.search(r"(?:rankClass|wnGroup|jo)\D{0,20}([1-5]).{0,100}(?:rankNo|wnNo|winningNo)\D{0,20}(\d{6})", raw, re.I | re.S)
        if m:
            first_digits = [int(m.group(1)), *map(int, m.group(2))]
    if bonus_digits is None:
        raw = "\n".join((s.string or "") for s in soup.find_all("script"))
        m = re.search(r"(?:bonus|bns).{0,100}(?:rankNo|wnNo|winningNo)?\D{0,20}(\d{6})", raw, re.I | re.S)
        if m:
            bonus_digits = list(map(int, m.group(1)))

    if first_digits is None or bonus_digits is None:
        raise RuntimeError("Pension720 first/bonus digits not found in official HTML")
    group = first_digits[0]
    first_no = "".join(map(str, first_digits[1:7]))
    bonus_no = "".join(map(str, bonus_digits[:6]))
    return _build_pension_rows(round_no, group, first_no, bonus_no, draw_date)


def fetch_pension(round_no: int) -> list[dict[str, Any]]:
    errors: list[str] = []
    json_urls = [
        f"{BASE}/pt720/selectPstPt720Info.do?srchPsltEpsd={round_no}",
        f"{BASE}/pt720/selectPstPt720Info.do?psltEpsd={round_no}",
        f"{BASE}/pt720/selectPstPt720InfoNew.do?srchPsltEpsd={round_no}",
    ]
    for url in json_urls:
        try:
            payload = _request(url).json()
            rows = _pension_rows_from_json(payload, round_no)
            ranks = {r["rank"] for r in rows}
            if {1, 2, 3, 4, 5, 6, 7}.issubset(ranks) and (21 in ranks or len(rows) >= 8):
                for r in rows:
                    if not r.get("draw_date"):
                        r["draw_date"] = _infer_pension_date(round_no)
                return sorted(rows, key=lambda x: x["rank"])
        except Exception as e:
            errors.append(f"{url}: {e}")

    url = f"{BASE}/pt720/result?psltEpsd={round_no}"
    try:
        return parse_pension_html(_request(url).text, round_no)
    except Exception as e:
        errors.append(f"{url}: {e}")
    raise RuntimeError(" | ".join(errors))


def replace_pension_results(c: sqlite3.Connection, round_no: int, rows: list[dict[str, Any]]) -> None:
    ranks = {int(r["rank"]) for r in rows}
    if not {1, 2, 3, 4, 5, 6, 7, 21}.issubset(ranks):
        raise ValueError("Pension720 payload is incomplete")
    c.execute("DELETE FROM pension_results WHERE round=?", (round_no,))
    c.executemany(
        """INSERT INTO pension_results(round,rank,rank_class,rank_no,prize_amount,winner_count,draw_date)
           VALUES(?,?,?,?,?,?,?)""",
        [(
            round_no, int(r["rank"]), str(r.get("rank_class") or ""), str(r["rank_no"]),
            r.get("prize_amount"), r.get("winner_count"), r.get("draw_date") or _infer_pension_date(round_no),
        ) for r in rows],
    )


# ---------------- Orchestration ----------------


def _update_new_lotto(c: sqlite3.Connection, max_rounds: int, updated: list[int]) -> None:
    local = c.execute("SELECT COALESCE(MAX(round),0) FROM lotto_draws").fetchone()[0]
    target = min(expected_latest_lotto(), local + max_rounds)
    for rd in range(local + 1, target + 1):
        try:
            d = fetch_lotto(rd)
        except Exception as e:
            log(c, "lotto", rd, "FAILED", str(e))
            c.commit()
            break
        try:
            upsert_lotto(c, d)
            set_state(c, "lotto", rd)
            log(c, "lotto", rd, "SUCCESS", "dhlottery official")
            c.commit()
            updated.append(rd)
        except Exception:
            c.rollback()
            raise


def _repair_lotto_stores(c: sqlite3.Connection, max_rounds: int, updated: list[int]) -> None:
    latest_draw = c.execute("SELECT COALESCE(MAX(round),0) FROM lotto_draws").fetchone()[0]
    current = state(c, "lotto_stores")
    for rd in range(current + 1, min(latest_draw, current + max_rounds) + 1):
        draw = c.execute("SELECT first_winners,second_winners FROM lotto_draws WHERE round=?", (rd,)).fetchone()
        if not draw:
            break
        try:
            rows = fetch_winning_stores(rd, "lt645", draw[0], draw[1])
            replace_lotto_stores(c, rd, rows)
            set_state(c, "lotto_stores", rd)
            log(c, "lotto_stores", rd, "SUCCESS", f"{len(rows)} rows")
            c.commit()
            updated.append(rd)
        except Exception as e:
            c.rollback()
            log(c, "lotto_stores", rd, "FAILED", str(e))
            c.commit()
            break


def _update_new_pension(c: sqlite3.Connection, max_rounds: int, updated: list[int]) -> None:
    local = c.execute("SELECT COALESCE(MAX(round),0) FROM pension_results").fetchone()[0]
    target = min(expected_latest_pension(), local + max_rounds)
    for rd in range(local + 1, target + 1):
        try:
            rows = fetch_pension(rd)
            replace_pension_results(c, rd, rows)
            set_state(c, "pension", rd)
            log(c, "pension", rd, "SUCCESS", "dhlottery official")
            c.commit()
            updated.append(rd)
        except Exception as e:
            c.rollback()
            log(c, "pension", rd, "FAILED", str(e))
            c.commit()
            break


def _repair_pension_stores(c: sqlite3.Connection, max_rounds: int, updated: list[int]) -> None:
    latest_draw = c.execute("SELECT COALESCE(MAX(round),0) FROM pension_results").fetchone()[0]
    current = state(c, "pension_stores")
    for rd in range(current + 1, min(latest_draw, current + max_rounds) + 1):
        try:
            rows = fetch_winning_stores(rd, "pt720")
            replace_pension_stores(c, rd, rows)
            set_state(c, "pension_stores", rd)
            log(c, "pension_stores", rd, "SUCCESS", f"{len(rows)} rows")
            c.commit()
            updated.append(rd)
        except Exception as e:
            c.rollback()
            log(c, "pension_stores", rd, "FAILED", str(e))
            c.commit()
            break


def run(max_rounds: int = 3) -> dict[str, list[int]]:
    result = {"lotto": [], "lotto_stores": [], "pension": [], "pension_stores": []}
    with sqlite3.connect(DB, timeout=30) as c:
        c.execute("PRAGMA busy_timeout=5000")
        c.execute("PRAGMA journal_mode=WAL")
        ensure_schema(c)
        _update_new_lotto(c, max_rounds, result["lotto"])
        _repair_lotto_stores(c, max_rounds, result["lotto_stores"])
        _update_new_pension(c, max_rounds, result["pension"])
        _repair_pension_stores(c, max_rounds, result["pension_stores"])
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Update LottoInsight from official dhlottery sources")
    parser.add_argument("--max-rounds", type=int, default=12, help="maximum missing rounds to process per dataset")
    args = parser.parse_args()
    print(json.dumps(run(max_rounds=max(1, args.max_rounds)), ensure_ascii=False))
