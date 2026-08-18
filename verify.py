import hashlib
import json
import sqlite3
from pathlib import Path

root = Path(__file__).parent
app_db = root / 'android/app/src/main/assets/databases/lotto_app.db'
server_db = root / 'data/seed/lotto_app.db'


def inspect(path):
    c = sqlite3.connect(path)
    try:
        cols = {r[1] for r in c.execute('PRAGMA table_info(saved_tickets)')}
        checks = {
            'integrity': c.execute('PRAGMA integrity_check').fetchone()[0],
            'lotto_draws': c.execute('SELECT COUNT(*) FROM lotto_draws').fetchone()[0],
            'latest_lotto': c.execute('SELECT MAX(round) FROM lotto_draws').fetchone()[0],
            'lotto_winning_stores': c.execute('SELECT COUNT(*) FROM lotto_winning_stores').fetchone()[0],
            'stores': c.execute('SELECT COUNT(*) FROM stores').fetchone()[0],
            'pension_results': c.execute('SELECT COUNT(*) FROM pension_results').fetchone()[0],
            'latest_pension': c.execute('SELECT MAX(round) FROM pension_results').fetchone()[0],
            'pension_winning_stores': c.execute('SELECT COUNT(*) FROM pension_winning_stores').fetchone()[0],
            'duplicate_lotto_rounds': c.execute('SELECT COUNT(*) FROM (SELECT round FROM lotto_draws GROUP BY round HAVING COUNT(*)>1)').fetchone()[0],
            'saved_ticket_columns': sorted(cols),
            'sync_states': dict(c.execute('SELECT dataset,latest_round FROM sync_state')),
        }
        return checks
    finally:
        c.close()

report = {'app_db': inspect(app_db), 'seed_db': inspect(server_db)}
report['same_seed_sha256'] = hashlib.sha256(app_db.read_bytes()).hexdigest() == hashlib.sha256(server_db.read_bytes()).hexdigest()
print(json.dumps(report, ensure_ascii=False, indent=2))
for side in ('app_db', 'seed_db'):
    assert report[side]['integrity'] == 'ok'
    assert report[side]['duplicate_lotto_rounds'] == 0
    assert {'source', 'score'}.issubset(report[side]['saved_ticket_columns'])
    assert {'lotto', 'lotto_stores', 'pension', 'pension_stores'}.issubset(report[side]['sync_states'])
assert report['same_seed_sha256']
