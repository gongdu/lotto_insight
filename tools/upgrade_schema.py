from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
DBS = [
    ROOT / 'server/data/lotto_app.db',
    ROOT / 'android/app/src/main/assets/databases/lotto_app.db',
]

SCHEMA = '''
CREATE TABLE IF NOT EXISTS saved_tickets(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 numbers TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 memo TEXT NOT NULL DEFAULT '',
 source TEXT NOT NULL DEFAULT 'manual',
 score REAL
);
CREATE INDEX IF NOT EXISTS idx_saved_tickets_created ON saved_tickets(created_at DESC);
'''

def has_column(c, table, col):
    return any(r[1] == col for r in c.execute(f'PRAGMA table_info({table})'))

def upgrade(path: Path):
    c = sqlite3.connect(path)
    try:
        c.executescript(SCHEMA)
        if not has_column(c, 'saved_tickets', 'source'):
            c.execute("ALTER TABLE saved_tickets ADD COLUMN source TEXT NOT NULL DEFAULT 'manual'")
        if not has_column(c, 'saved_tickets', 'score'):
            c.execute('ALTER TABLE saved_tickets ADD COLUMN score REAL')
        states = {
            'lotto': c.execute('SELECT COALESCE(MAX(round),0) FROM lotto_draws').fetchone()[0],
            'lotto_stores': c.execute('SELECT COALESCE(MAX(round),0) FROM lotto_winning_stores').fetchone()[0],
            'pension': c.execute('SELECT COALESCE(MAX(round),0) FROM pension_results').fetchone()[0],
            'pension_stores': c.execute("SELECT COALESCE(MAX(round),0) FROM pension_winning_stores WHERE lottery_type='PensionLottery720'").fetchone()[0],
        }
        for ds, latest in states.items():
            c.execute('''INSERT INTO sync_state(dataset,latest_round,updated_at) VALUES(?,?,CURRENT_TIMESTAMP)
                         ON CONFLICT(dataset) DO UPDATE SET latest_round=MAX(sync_state.latest_round,excluded.latest_round),updated_at=CURRENT_TIMESTAMP''', (ds, latest))
        c.commit()
        print(path, 'ok', c.execute('PRAGMA integrity_check').fetchone()[0], states)
    finally:
        c.close()

for db in DBS:
    upgrade(db)
