from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

KST = ZoneInfo('Asia/Seoul')


def connect(path: Path) -> sqlite3.Connection:
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    return c


def state(c: sqlite3.Connection, dataset: str, fallback: str) -> int:
    row = c.execute('SELECT latest_round FROM sync_state WHERE dataset=?', (dataset,)).fetchone()
    return int(row[0]) if row else int(c.execute(fallback).fetchone()[0] or 0)


def states(c: sqlite3.Connection) -> dict[str, int]:
    return {
        'lotto': state(c, 'lotto', 'SELECT COALESCE(MAX(round),0) FROM lotto_draws'),
        'lotto_stores': state(c, 'lotto_stores', 'SELECT COALESCE(MAX(round),0) FROM lotto_winning_stores'),
        'pension': state(c, 'pension', 'SELECT COALESCE(MAX(round),0) FROM pension_results'),
        'pension_stores': state(c, 'pension_stores', "SELECT COALESCE(MAX(round),0) FROM pension_winning_stores WHERE lottery_type='PensionLottery720'"),
    }


def draw_json(r: sqlite3.Row) -> dict:
    return {
        'round': r['round'],
        'date': r['draw_date'],
        'numbers': [r[f'n{i}'] for i in range(1, 7)],
        'bonus': r['bonus'],
        'first_prize': r['first_prize'],
        'first_winners': r['first_winners'],
        'total_sales': r['total_sales'],
        'auto': r['first_auto'],
        'manual': r['first_manual'],
        'half': r['first_half_auto'],
        'second_prize': r['second_prize'],
        'second_winners': r['second_winners'],
        'third_prize': r['third_prize'],
        'third_winners': r['third_winners'],
        'fourth_prize': r['fourth_prize'],
        'fourth_winners': r['fourth_winners'],
        'fifth_prize': r['fifth_prize'],
        'fifth_winners': r['fifth_winners'],
    }


def dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(',', ':'), sort_keys=True) + '\n', encoding='utf-8')


def export_round_files(c: sqlite3.Connection, base: dict[str, int], current: dict[str, int], site: Path) -> None:
    for rd in range(base['lotto'] + 1, current['lotto'] + 1):
        r = c.execute('SELECT * FROM lotto_draws WHERE round=?', (rd,)).fetchone()
        if not r:
            raise RuntimeError(f'missing lotto round {rd}')
        dump(site / 'data/lotto' / f'{rd}.json', draw_json(r))

    for rd in range(base['lotto_stores'] + 1, current['lotto_stores'] + 1):
        rows = c.execute(
            '''SELECT round,rank,store_id,name,phone,region,address,auto_possible,latitude,longitude
               FROM lotto_winning_stores WHERE round=? ORDER BY rank,id''', (rd,)
        ).fetchall()
        if not rows:
            raise RuntimeError(f'missing lotto store round {rd}')
        dump(site / 'data/lotto-stores' / f'{rd}.json', {'round': rd, 'items': [dict(r) for r in rows]})

    for rd in range(base['pension'] + 1, current['pension'] + 1):
        rows = c.execute(
            '''SELECT round,rank,rank_class,rank_no,prize_amount,winner_count,draw_date
               FROM pension_results WHERE round=? ORDER BY rank,id''', (rd,)
        ).fetchall()
        if not rows:
            raise RuntimeError(f'missing pension round {rd}')
        dump(site / 'data/pension' / f'{rd}.json', {'round': rd, 'items': [dict(r) for r in rows]})

    for rd in range(base['pension_stores'] + 1, current['pension_stores'] + 1):
        rows = c.execute(
            '''SELECT round,store_id,name,address,phone,region,latitude,longitude,winning_rank,winning_store_rank
               FROM pension_winning_stores
               WHERE lottery_type='PensionLottery720' AND round=?
               ORDER BY winning_rank,winning_store_rank,id''', (rd,)
        ).fetchall()
        # A valid published round can legitimately contain zero winning-store rows.
        dump(site / 'data/pension-stores' / f'{rd}.json', {'round': rd, 'items': [dict(r) for r in rows]})


def export_site(db_path: Path, seed_path: Path, site: Path, publish_db: bool) -> dict:
    site.mkdir(parents=True, exist_ok=True)
    (site / '.nojekyll').touch()
    with connect(seed_path) as seed, connect(db_path) as c:
        base = states(seed)
        current = states(c)
        for key in current:
            if current[key] < base[key]:
                raise RuntimeError(f'{key}: current state {current[key]} < seed {base[key]}')
        export_round_files(c, base, current, site)
        latest_draw = c.execute('SELECT * FROM lotto_draws ORDER BY round DESC LIMIT 1').fetchone()
        latest_pension = c.execute('SELECT MAX(round) FROM pension_results').fetchone()[0]

    generated = datetime.now(KST).isoformat(timespec='seconds')
    manifest = {
        'schema_version': 1,
        'generated_at': generated,
        'seed_state': base,
        'datasets': {k: {'latest_round': v} for k, v in current.items()},
        'paths': {
            'lotto': 'data/lotto/{round}.json',
            'lotto_stores': 'data/lotto-stores/{round}.json',
            'pension': 'data/pension/{round}.json',
            'pension_stores': 'data/pension-stores/{round}.json',
        },
    }
    dump(site / 'manifest.json', manifest)
    if latest_draw:
        dump(site / 'latest.json', draw_json(latest_draw))
    dump(site / 'health.json', {
        'ok': True,
        'generated_at': generated,
        **current,
        'latest_pension': int(latest_pension or 0),
    })

    if publish_db:
        target = site / 'downloads/lotto_app.db'
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(db_path, target)

    return manifest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', required=True, type=Path)
    ap.add_argument('--seed-db', required=True, type=Path)
    ap.add_argument('--site', default='public', type=Path)
    ap.add_argument('--publish-db', action='store_true')
    args = ap.parse_args()
    manifest = export_site(args.db, args.seed_db, args.site, args.publish_db)
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == '__main__':
    main()
