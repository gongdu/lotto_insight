package com.example.lottoinsight

import android.content.ContentValues
import android.content.Context
import android.database.Cursor
import android.database.sqlite.SQLiteDatabase
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

class LotteryDb(private val context: Context) {
    private val name = "lotto_app.db"
    private val file: File get() = context.getDatabasePath(name)
    @Volatile private var database: SQLiteDatabase? = null

    @Synchronized
    fun db(): SQLiteDatabase {
        database?.takeIf { it.isOpen }?.let { return it }
        if (!file.exists()) {
            file.parentFile?.mkdirs()
            context.assets.open("databases/$name").use { input ->
                file.outputStream().use { output -> input.copyTo(output) }
            }
        }
        return SQLiteDatabase.openDatabase(file.path, null, SQLiteDatabase.OPEN_READWRITE).also {
            database = it
            ensureSchema(it)
        }
    }

    private fun ensureSchema(d: SQLiteDatabase) {
        d.execSQL(
            """CREATE TABLE IF NOT EXISTS saved_tickets(
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               numbers TEXT NOT NULL,
               created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
               memo TEXT NOT NULL DEFAULT '',
               source TEXT NOT NULL DEFAULT 'manual',
               score REAL)""".trimIndent()
        )
        if (!hasColumn(d, "saved_tickets", "source")) {
            d.execSQL("ALTER TABLE saved_tickets ADD COLUMN source TEXT NOT NULL DEFAULT 'manual'")
        }
        if (!hasColumn(d, "saved_tickets", "score")) {
            d.execSQL("ALTER TABLE saved_tickets ADD COLUMN score REAL")
        }
        d.execSQL("CREATE INDEX IF NOT EXISTS idx_saved_tickets_created ON saved_tickets(created_at DESC)")
        d.execSQL("CREATE TABLE IF NOT EXISTS sync_state(dataset TEXT PRIMARY KEY, latest_round INTEGER NOT NULL DEFAULT 0, updated_at TEXT)")
        d.execSQL("CREATE TABLE IF NOT EXISTS update_log(id INTEGER PRIMARY KEY AUTOINCREMENT,dataset TEXT NOT NULL,round INTEGER,status TEXT NOT NULL,message TEXT,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")

        val seedStates = mapOf(
            "lotto" to scalarInt(d, "SELECT COALESCE(MAX(round),0) FROM lotto_draws"),
            "lotto_stores" to scalarInt(d, "SELECT COALESCE(MAX(round),0) FROM lotto_winning_stores"),
            "pension" to scalarInt(d, "SELECT COALESCE(MAX(round),0) FROM pension_results"),
            "pension_stores" to scalarInt(d, "SELECT COALESCE(MAX(round),0) FROM pension_winning_stores WHERE lottery_type='PensionLottery720'")
        )
        seedStates.forEach { (dataset, round) ->
            if (syncState(dataset) == 0 && round > 0) setSyncState(dataset, round, d)
        }
    }

    private fun hasColumn(d: SQLiteDatabase, table: String, column: String): Boolean =
        d.rawQuery("PRAGMA table_info($table)", null).use { c ->
            var found = false
            while (c.moveToNext()) if (c.getString(1) == column) found = true
            found
        }

    private fun scalarInt(d: SQLiteDatabase, sql: String): Int =
        d.rawQuery(sql, null).use { c -> if (c.moveToFirst()) c.getInt(0) else 0 }

    fun latestDraw(): LottoDraw? = db().rawQuery(
        "SELECT * FROM lotto_draws ORDER BY round DESC LIMIT 1", null
    ).use { c -> if (c.moveToFirst()) c.toDraw() else null }

    fun draw(round: Int): LottoDraw? = db().rawQuery(
        "SELECT * FROM lotto_draws WHERE round=?", arrayOf(round.toString())
    ).use { c -> if (c.moveToFirst()) c.toDraw() else null }

    fun draws(limit: Int = 200, query: String = ""): List<LottoDraw> {
        val round = query.trim().toIntOrNull()
        val sql = if (round != null) {
            "SELECT * FROM lotto_draws WHERE round=? ORDER BY round DESC"
        } else {
            "SELECT * FROM lotto_draws ORDER BY round DESC LIMIT ?"
        }
        val args = if (round != null) arrayOf(round.toString()) else arrayOf(limit.toString())
        return db().rawQuery(sql, args).use { c -> buildList { while (c.moveToNext()) add(c.toDraw()) } }
    }

    fun allNumbers(): List<List<Int>> = db().rawQuery(
        "SELECT n1,n2,n3,n4,n5,n6 FROM lotto_draws ORDER BY round", null
    ).use { c -> buildList { while (c.moveToNext()) add((0..5).map(c::getInt)) } }

    fun stores(query: String, limit: Int = 100): List<WinningStore> {
        val s = "%${query.trim()}%"
        return db().rawQuery(
            """SELECT round,rank,name,COALESCE(region,''),COALESCE(address,''),COALESCE(auto_possible,'')
               FROM lotto_winning_stores
               WHERE name LIKE ? OR region LIKE ? OR address LIKE ?
               ORDER BY round DESC,rank,id LIMIT ?""".trimIndent(),
            arrayOf(s, s, s, limit.toString())
        ).use { c ->
            buildList {
                while (c.moveToNext()) add(
                    WinningStore(c.getInt(0), c.getInt(1), c.getString(2), c.getString(3), c.getString(4), c.getString(5))
                )
            }
        }
    }

    fun pension(round: Int? = null): List<PensionResult> {
        val sql = if (round == null) {
            """SELECT round,rank,rank_class,rank_no,prize_amount,winner_count,draw_date
               FROM pension_results WHERE round=(SELECT MAX(round) FROM pension_results) ORDER BY rank""".trimIndent()
        } else {
            """SELECT round,rank,rank_class,rank_no,prize_amount,winner_count,draw_date
               FROM pension_results WHERE round=? ORDER BY rank""".trimIndent()
        }
        return db().rawQuery(sql, if (round == null) null else arrayOf(round.toString())).use { c ->
            buildList {
                while (c.moveToNext()) add(
                    PensionResult(
                        c.getInt(0), c.getInt(1), c.getString(2), c.getString(3),
                        if (c.isNull(4)) null else c.getLong(4),
                        if (c.isNull(5)) null else c.getInt(5), c.getString(6)
                    )
                )
            }
        }
    }

    fun saveTicket(numbers: List<Int>, memo: String = "", source: String = "manual", score: Double? = null): Long {
        val clean = numbers.distinct().sorted()
        require(clean.size == 6 && clean.all { it in 1..45 }) { "1~45 사이 서로 다른 번호 6개가 필요합니다." }
        val v = ContentValues().apply {
            put("numbers", clean.joinToString(","))
            put("memo", memo.trim())
            put("source", source)
            if (score == null) putNull("score") else put("score", score)
        }
        return db().insertOrThrow("saved_tickets", null, v)
    }

    fun tickets(): List<SavedTicket> = db().rawQuery(
        "SELECT id,numbers,created_at,memo,source,score FROM saved_tickets ORDER BY id DESC", null
    ).use { c ->
        buildList {
            while (c.moveToNext()) {
                add(
                    SavedTicket(
                        id = c.getLong(0),
                        numbers = parseNumbers(c.getString(1)),
                        createdAt = c.getString(2),
                        memo = c.getString(3),
                        source = c.getString(4),
                        score = if (c.isNull(5)) null else c.getDouble(5)
                    )
                )
            }
        }
    }

    fun deleteTicket(id: Long) {
        db().delete("saved_tickets", "id=?", arrayOf(id.toString()))
    }

    fun ticketChecks(round: Int): List<TicketCheck> {
        val draw = draw(round) ?: return emptyList()
        return tickets().map { ticket ->
            val (rank, matchCount, bonus) = TicketMatcher.check(ticket.numbers, draw)
            TicketCheck(ticket, draw, rank, matchCount, bonus)
        }
    }

    fun syncState(dataset: String): Int = db().rawQuery(
        "SELECT latest_round FROM sync_state WHERE dataset=?", arrayOf(dataset)
    ).use { c -> if (c.moveToFirst()) c.getInt(0) else 0 }

    fun setSyncState(dataset: String, round: Int) = setSyncState(dataset, round, db())

    private fun setSyncState(dataset: String, round: Int, d: SQLiteDatabase) {
        val v = ContentValues().apply {
            put("dataset", dataset)
            put("latest_round", round)
            put("updated_at", System.currentTimeMillis().toString())
        }
        d.insertWithOnConflict("sync_state", null, v, SQLiteDatabase.CONFLICT_REPLACE)
    }

    fun upsertDraws(items: JSONArray) {
        val d = db()
        d.beginTransaction()
        try {
            for (i in 0 until items.length()) upsertDrawJson(items.getJSONObject(i), d)
            d.setTransactionSuccessful()
        } finally {
            d.endTransaction()
        }
    }

    private fun upsertDrawJson(o: JSONObject, d: SQLiteDatabase) {
        val numbers = o.getJSONArray("numbers")
        val v = ContentValues().apply {
            put("round", o.getInt("round"))
            put("draw_date", o.optString("date", ""))
            for (i in 0..5) put("n${i + 1}", numbers.getInt(i))
            put("bonus", o.getInt("bonus"))
            putNullable("first_prize", o.longOrNull("first_prize"))
            putNullable("first_winners", o.intOrNull("first_winners"))
            putNullable("total_sales", o.longOrNull("total_sales"))
            putNullable("first_auto", o.intOrNull("auto"))
            putNullable("first_manual", o.intOrNull("manual"))
            putNullable("first_half_auto", o.intOrNull("half"))
            putNullable("second_prize", o.longOrNull("second_prize"))
            putNullable("second_winners", o.intOrNull("second_winners"))
            putNullable("third_prize", o.longOrNull("third_prize"))
            putNullable("third_winners", o.intOrNull("third_winners"))
            putNullable("fourth_prize", o.longOrNull("fourth_prize"))
            putNullable("fourth_winners", o.intOrNull("fourth_winners"))
            putNullable("fifth_prize", o.longOrNull("fifth_prize"))
            putNullable("fifth_winners", o.intOrNull("fifth_winners"))
            put("updated_at", System.currentTimeMillis().toString())
        }
        d.insertWithOnConflict("lotto_draws", null, v, SQLiteDatabase.CONFLICT_REPLACE)
    }

    fun replaceLottoStores(round: Int, items: JSONArray) {
        val d = db()
        d.beginTransaction()
        try {
            d.delete("lotto_winning_stores", "round=?", arrayOf(round.toString()))
            for (i in 0 until items.length()) {
                val o = items.getJSONObject(i)
                val v = ContentValues().apply {
                    put("round", round)
                    put("rank", o.optInt("rank", 0))
                    putNullable("store_id", o.stringOrNull("store_id"))
                    put("name", o.optString("name", ""))
                    putNullable("phone", o.stringOrNull("phone"))
                    putNullable("region", o.stringOrNull("region"))
                    putNullable("address", o.stringOrNull("address"))
                    putNullable("auto_possible", o.stringOrNull("auto_possible"))
                    putNullable("latitude", o.doubleOrNull("latitude"))
                    putNullable("longitude", o.doubleOrNull("longitude"))
                }
                d.insertOrThrow("lotto_winning_stores", null, v)
            }
            d.setTransactionSuccessful()
        } finally {
            d.endTransaction()
        }
    }

    fun replacePensionResults(round: Int, items: JSONArray) {
        val d = db()
        d.beginTransaction()
        try {
            d.delete("pension_results", "round=?", arrayOf(round.toString()))
            for (i in 0 until items.length()) {
                val o = items.getJSONObject(i)
                val v = ContentValues().apply {
                    put("round", round)
                    put("rank", o.getInt("rank"))
                    put("rank_class", o.optString("rank_class", ""))
                    put("rank_no", o.getString("rank_no"))
                    putNullable("prize_amount", o.longOrNull("prize_amount"))
                    putNullable("winner_count", o.intOrNull("winner_count"))
                    put("draw_date", o.optString("draw_date", ""))
                }
                d.insertOrThrow("pension_results", null, v)
            }
            d.setTransactionSuccessful()
        } finally {
            d.endTransaction()
        }
    }

    fun replacePensionStores(round: Int, items: JSONArray) {
        val d = db()
        d.beginTransaction()
        try {
            d.delete("pension_winning_stores", "lottery_type='PensionLottery720' AND round=?", arrayOf(round.toString()))
            for (i in 0 until items.length()) {
                val o = items.getJSONObject(i)
                val v = ContentValues().apply {
                    put("lottery_type", "PensionLottery720")
                    put("round", round)
                    putNullable("store_id", o.stringOrNull("store_id"))
                    put("name", o.optString("name", ""))
                    putNullable("address", o.stringOrNull("address"))
                    putNullable("phone", o.stringOrNull("phone"))
                    putNullable("region", o.stringOrNull("region"))
                    putNullable("latitude", o.doubleOrNull("latitude"))
                    putNullable("longitude", o.doubleOrNull("longitude"))
                    putNullable("winning_rank", o.intOrNull("winning_rank"))
                    putNullable("winning_store_rank", o.intOrNull("winning_store_rank"))
                }
                d.insertOrThrow("pension_winning_stores", null, v)
            }
            d.setTransactionSuccessful()
        } finally {
            d.endTransaction()
        }
    }

    private fun parseNumbers(s: String): List<Int> = s.split(',').mapNotNull { it.trim().toIntOrNull() }.sorted()

    private fun Cursor.toDraw() = LottoDraw(
        getInt(getColumnIndexOrThrow("round")),
        getString(getColumnIndexOrThrow("draw_date")),
        listOf("n1", "n2", "n3", "n4", "n5", "n6").map { getInt(getColumnIndexOrThrow(it)) },
        getInt(getColumnIndexOrThrow("bonus")),
        nullableLong("first_prize"), nullableInt("first_winners"), nullableInt("first_auto"), nullableInt("first_manual"), nullableInt("first_half_auto")
    )

    private fun Cursor.nullableLong(column: String): Long? = getColumnIndexOrThrow(column).let { if (isNull(it)) null else getLong(it) }
    private fun Cursor.nullableInt(column: String): Int? = getColumnIndexOrThrow(column).let { if (isNull(it)) null else getInt(it) }

    private fun JSONObject.longOrNull(key: String): Long? = if (has(key) && !isNull(key)) getLong(key) else null
    private fun JSONObject.intOrNull(key: String): Int? = if (has(key) && !isNull(key)) getInt(key) else null
    private fun JSONObject.doubleOrNull(key: String): Double? = if (has(key) && !isNull(key)) getDouble(key) else null
    private fun JSONObject.stringOrNull(key: String): String? = if (has(key) && !isNull(key)) getString(key) else null

    private fun ContentValues.putNullable(key: String, value: Long?) { if (value == null) putNull(key) else put(key, value) }
    private fun ContentValues.putNullable(key: String, value: Int?) { if (value == null) putNull(key) else put(key, value) }
    private fun ContentValues.putNullable(key: String, value: Double?) { if (value == null) putNull(key) else put(key, value) }
    private fun ContentValues.putNullable(key: String, value: String?) { if (value == null) putNull(key) else put(key, value) }
}
