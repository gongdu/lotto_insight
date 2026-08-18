package com.example.lottoinsight
import android.app.Application
class LottoApp:Application(){ override fun onCreate(){ super.onCreate(); LotteryDb(this).db().close(); SyncWorker.schedule(this) } }
