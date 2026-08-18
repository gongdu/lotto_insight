package com.example.lottoinsight

import android.content.Context
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.TimeUnit

object SyncConfig {
    fun get(context: Context): String {
        val saved = context.getSharedPreferences("sync", Context.MODE_PRIVATE)
            .getString("base_url", null)?.trim().orEmpty().trimEnd('/')
        return if (saved.isNotBlank()) saved else BuildConfig.PAGES_BASE_URL.trim().trimEnd('/')
    }

    fun set(context: Context, url: String) = context.getSharedPreferences("sync", Context.MODE_PRIVATE)
        .edit().putString("base_url", url.trim().trimEnd('/')).apply()
}

class SyncWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {
    override suspend fun doWork(): Result = try {
        if (SyncConfig.get(applicationContext).isBlank()) return Result.success()
        SyncClient(applicationContext).sync()
        Result.success()
    } catch (_: Exception) {
        Result.retry()
    }

    companion object {
        fun schedule(context: Context) {
            val request = PeriodicWorkRequestBuilder<SyncWorker>(12, TimeUnit.HOURS)
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                "lottery-sync", ExistingPeriodicWorkPolicy.UPDATE, request
            )
        }
    }
}

class SyncClient(private val context: Context) {
    fun sync(): SyncSummary {
        val base = SyncConfig.get(context)
        if (base.isBlank()) return SyncSummary()
        val db = LotteryDb(context)
        val manifest = getJson("$base/manifest.json?t=${System.currentTimeMillis()}")
        if (manifest.optInt("schema_version", 0) != 1) error("지원하지 않는 데이터 스키마입니다.")
        val datasets = manifest.getJSONObject("datasets")

        var lottoDraws = 0
        var lottoStores = 0
        var pensionRows = 0
        var pensionStores = 0

        run {
            val after = db.syncState("lotto")
            val latest = datasets.getJSONObject("lotto").getInt("latest_round")
            for (round in (after + 1)..latest) {
                val item = getJson("$base/data/lotto/$round.json")
                db.upsertDraws(JSONArray().put(item))
                db.setSyncState("lotto", round)
                lottoDraws++
            }
        }

        run {
            val after = db.syncState("lotto_stores")
            val latest = datasets.getJSONObject("lotto_stores").getInt("latest_round")
            for (round in (after + 1)..latest) {
                val block = getJson("$base/data/lotto-stores/$round.json")
                val items = block.getJSONArray("items")
                db.replaceLottoStores(round, items)
                db.setSyncState("lotto_stores", round)
                lottoStores += items.length()
            }
        }

        run {
            val after = db.syncState("pension")
            val latest = datasets.getJSONObject("pension").getInt("latest_round")
            for (round in (after + 1)..latest) {
                val block = getJson("$base/data/pension/$round.json")
                val items = block.getJSONArray("items")
                db.replacePensionResults(round, items)
                db.setSyncState("pension", round)
                pensionRows += items.length()
            }
        }

        run {
            val after = db.syncState("pension_stores")
            val latest = datasets.getJSONObject("pension_stores").getInt("latest_round")
            for (round in (after + 1)..latest) {
                val block = getJson("$base/data/pension-stores/$round.json")
                val items = block.getJSONArray("items")
                db.replacePensionStores(round, items)
                db.setSyncState("pension_stores", round)
                pensionStores += items.length()
            }
        }

        return SyncSummary(lottoDraws, lottoStores, pensionRows, pensionStores)
    }

    private fun getJson(url: String): JSONObject {
        val connection = (URL(url).openConnection() as HttpURLConnection).apply {
            connectTimeout = 10_000
            readTimeout = 20_000
            requestMethod = "GET"
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Cache-Control", "no-cache")
        }
        try {
            if (connection.responseCode !in 200..299) error("HTTP ${connection.responseCode}: $url")
            return JSONObject(connection.inputStream.bufferedReader().use { it.readText() })
        } finally {
            connection.disconnect()
        }
    }
}
