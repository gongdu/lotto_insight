from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def load(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def put_state(c: sqlite3.Connection, dataset: str, rd: int) -> None:
    c.execute(
        '''INSERT INTO sync_state(dataset,latest_round,updated_at) VALUES(?,?,CURRENT_TIMESTAMP)
           ON CONFLICT(dataset) DO UPDATE SET latest_round=excluded.latest_round,updated_at=CURRENT_TIMESTAMP''',
        (dataset, rd),
    )


def apply_lotto(c: sqlite3.Connection, o: dict) -> None:
    nums = o['numbers']
    c.execute(
        '''INSERT INTO lotto_draws(round,draw_date,n1,n2,n3,n4,n5,n6,bonus,first_prize,first_winners,total_sales,
          first_auto,first_manual,first_half_auto,second_prize,second_winners,third_prize,third_winners,
          fourth_prize,fourth_winners,fifth_prize,fifth_winners)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(round) DO UPDATE SET draw_date=excluded.draw_date,n1=excluded.n1,n2=excluded.n2,n3=excluded.n3,
          n4=excluded.n4,n5=excluded.n5,n6=excluded.n6,bonus=excluded.bonus,first_prize=excluded.first_prize,
          first_winners=excluded.first_winners,total_sales=excluded.total_sales,first_auto=excluded.first_auto,
          first_manual=excluded.first_manual,first_half_auto=excluded.first_half_auto,second_prize=excluded.second_prize,
          second_winners=excluded.second_winners,third_prize=excluded.third_prize,third_winners=excluded.third_winners,
          fourth_prize=excluded.fourth_prize,fourth_winners=excluded.fourth_winners,fifth_prize=excluded.fifth_prize,
          fifth_winners=excluded.fifth_winners,updated_at=CURRENT_TIMESTAMP''',
        (o['round'], o.get('date',''), *nums, o['bonus'], o.get('first_prize'), o.get('first_winners'), o.get('total_sales'),
         o.get('auto'), o.get('manual'), o.get('half'), o.get('second_prize'), o.get('second_winners'), o.get('third_prize'),
         o.get('third_winners'), o.get('fourth_prize'), o.get('fourth_winners'), o.get('fifth_prize'), o.get('fifth_winners')),
    )


def apply_site(db: Path, site: Path) -> None:
    with sqlite3.connect(db) as c:
        c.execute('PRAGMA busy_timeout=5000')
        c.execute('CREATE TABLE IF NOT EXISTS sync_state(dataset TEXT PRIMARY KEY, latest_round INTEGER NOT NULL DEFAULT 0, updated_at TEXT)')

        for p in sorted((site / 'data/lotto').glob('*.json'), key=lambda x: int(x.stem)):
            o = load(p)
            apply_lotto(c, o)
            put_state(c, 'lotto', int(o['round']))

        for p in sorted((site / 'data/lotto-stores').glob('*.json'), key=lambda x: int(x.stem)):
            o = load(p); rd = int(o['round'])
            c.execute('DELETE FROM lotto_winning_stores WHERE round=?', (rd,))
            c.executemany(
                '''INSERT INTO lotto_winning_stores(round,rank,store_id,name,phone,region,address,auto_possible,latitude,longitude)
                   VALUES(?,?,?,?,?,?,?,?,?,?)''',
                [(rd, x.get('rank'), x.get('store_id'), x.get('name',''), x.get('phone'), x.get('region'), x.get('address'),
                  x.get('auto_possible'), x.get('latitude'), x.get('longitude')) for x in o['items']],
            )
            put_state(c, 'lotto_stores', rd)

        for p in sorted((site / 'data/pension').glob('*.json'), key=lambda x: int(x.stem)):
            o = load(p); rd = int(o['round'])
            c.execute('DELETE FROM pension_results WHERE round=?', (rd,))
            c.executemany(
                '''INSERT INTO pension_results(round,rank,rank_class,rank_no,prize_amount,winner_count,draw_date)
                   VALUES(?,?,?,?,?,?,?)''',
                [(rd, x['rank'], x.get('rank_class',''), x['rank_no'], x.get('prize_amount'), x.get('winner_count'), x.get('draw_date','')) for x in o['items']],
            )
            put_state(c, 'pension', rd)

        for p in sorted((site / 'data/pension-stores').glob('*.json'), key=lambda x: int(x.stem)):
            o = load(p); rd = int(o['round'])
            c.execute("DELETE FROM pension_winning_stores WHERE lottery_type='PensionLottery720' AND round=?", (rd,))
            c.executemany(
                '''INSERT INTO pension_winning_stores(lottery_type,round,store_id,name,address,phone,region,latitude,longitude,winning_rank,winning_store_rank)
                   VALUES('PensionLottery720',?,?,?,?,?,?,?,?,?,?)''',
                [(rd, x.get('store_id'), x.get('name',''), x.get('address'), x.get('phone'), x.get('region'), x.get('latitude'),
                  x.get('longitude'), x.get('winning_rank'), x.get('winning_store_rank')) for x in o['items']],
            )
            put_state(c, 'pension_stores', rd)

        c.commit()
        result = c.execute('PRAGMA integrity_check').fetchone()[0]
        if result != 'ok':
            raise RuntimeError(f'integrity_check failed: {result}')


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', required=True, type=Path)
    ap.add_argument('--site', default='public', type=Path)
    args = ap.parse_args()
    apply_site(args.db, args.site)
    print('apply_site_updates: ok')


if __name__ == '__main__':
    main()
