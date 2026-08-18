from __future__ import annotations

import shutil
import sqlite3
import tempfile
from pathlib import Path

from apply_site_updates import apply_site
from export_pages import export_site, states

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / 'data/seed/lotto_app.db'


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        work = td / 'work.db'
        rebuilt = td / 'rebuilt.db'
        site = td / 'public'
        shutil.copy2(SEED, work)

        with sqlite3.connect(work) as c:
            # Synthetic next lotto draw.
            r = c.execute('SELECT * FROM lotto_draws ORDER BY round DESC LIMIT 1').fetchone()
            next_lotto = int(r[0]) + 1
            cols = [x[1] for x in c.execute('PRAGMA table_info(lotto_draws)')]
            vals = dict(zip(cols, r))
            vals['round'] = next_lotto
            vals['draw_date'] = '2099-01-01'
            vals['updated_at'] = '2099-01-01 00:00:00'
            keys = [k for k in cols if k != 'round']
            c.execute(
                f"INSERT INTO lotto_draws(round,{','.join(keys)}) VALUES(?,{','.join('?' for _ in keys)})",
                [next_lotto] + [vals[k] for k in keys],
            )
            c.execute("UPDATE sync_state SET latest_round=? WHERE dataset='lotto'", (next_lotto,))

            # Synthetic next lotto store round using one real store row.
            sr = c.execute('SELECT rank,store_id,name,phone,region,address,auto_possible,latitude,longitude FROM lotto_winning_stores ORDER BY round DESC,id LIMIT 1').fetchone()
            next_store = c.execute("SELECT latest_round FROM sync_state WHERE dataset='lotto_stores'").fetchone()[0] + 1
            c.execute('INSERT INTO lotto_winning_stores(round,rank,store_id,name,phone,region,address,auto_possible,latitude,longitude) VALUES(?,?,?,?,?,?,?,?,?,?)', (next_store, *sr))
            c.execute("UPDATE sync_state SET latest_round=? WHERE dataset='lotto_stores'", (next_store,))

            # Synthetic next pension result round.
            latest_p = c.execute('SELECT MAX(round) FROM pension_results').fetchone()[0]
            next_p = latest_p + 1
            rows = c.execute('SELECT rank,rank_class,rank_no,prize_amount,winner_count,draw_date FROM pension_results WHERE round=? ORDER BY rank', (latest_p,)).fetchall()
            c.executemany('INSERT INTO pension_results(round,rank,rank_class,rank_no,prize_amount,winner_count,draw_date) VALUES(?,?,?,?,?,?,?)', [(next_p, *x) for x in rows])
            c.execute("UPDATE sync_state SET latest_round=? WHERE dataset='pension'", (next_p,))

            # Synthetic next pension store round; zero rows is allowed, but add one to verify serialization.
            ps = c.execute("SELECT store_id,name,address,phone,region,latitude,longitude,winning_rank,winning_store_rank FROM pension_winning_stores WHERE lottery_type='PensionLottery720' ORDER BY round DESC,id LIMIT 1").fetchone()
            next_ps = c.execute("SELECT latest_round FROM sync_state WHERE dataset='pension_stores'").fetchone()[0] + 1
            if ps:
                c.execute("INSERT INTO pension_winning_stores(lottery_type,round,store_id,name,address,phone,region,latitude,longitude,winning_rank,winning_store_rank) VALUES('PensionLottery720',?,?,?,?,?,?,?,?,?,?)", (next_ps, *ps))
            c.execute("UPDATE sync_state SET latest_round=? WHERE dataset='pension_stores'", (next_ps,))
            c.commit()

        export_site(work, SEED, site, publish_db=False)
        shutil.copy2(SEED, rebuilt)
        apply_site(rebuilt, site)

        with sqlite3.connect(work) as a, sqlite3.connect(rebuilt) as b:
            assert states(a) == states(b)
            assert a.execute('SELECT COUNT(*) FROM lotto_draws').fetchone() == b.execute('SELECT COUNT(*) FROM lotto_draws').fetchone()
            assert a.execute('SELECT COUNT(*) FROM lotto_winning_stores').fetchone() == b.execute('SELECT COUNT(*) FROM lotto_winning_stores').fetchone()
            assert a.execute('SELECT COUNT(*) FROM pension_results').fetchone() == b.execute('SELECT COUNT(*) FROM pension_results').fetchone()
            assert a.execute("SELECT COUNT(*) FROM pension_winning_stores WHERE lottery_type='PensionLottery720'").fetchone() == b.execute("SELECT COUNT(*) FROM pension_winning_stores WHERE lottery_type='PensionLottery720'").fetchone()
            assert b.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'

        print('test_static_sync: ok')


if __name__ == '__main__':
    main()
