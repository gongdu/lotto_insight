package com.example.lottoinsight

import android.content.Context

object PredictionConfig {
    private const val PREF = "prediction_config"

    fun load(context: Context): PredictionSettings {
        val p = context.getSharedPreferences(PREF, Context.MODE_PRIVATE)
        return PredictionSettings(
            recentWindow = p.getInt("recentWindow", 60),
            sumMin = p.getInt("sumMin", 100),
            sumMax = p.getInt("sumMax", 180),
            oddMin = p.getInt("oddMin", 2),
            oddMax = p.getInt("oddMax", 4),
            lowMin = p.getInt("lowMin", 2),
            lowMax = p.getInt("lowMax", 4),
            maxConsecutive = p.getInt("maxConsecutive", 2)
        ).normalized()
    }

    fun save(context: Context, settings: PredictionSettings) {
        val s = settings.normalized()
        context.getSharedPreferences(PREF, Context.MODE_PRIVATE).edit()
            .putInt("recentWindow", s.recentWindow)
            .putInt("sumMin", s.sumMin)
            .putInt("sumMax", s.sumMax)
            .putInt("oddMin", s.oddMin)
            .putInt("oddMax", s.oddMax)
            .putInt("lowMin", s.lowMin)
            .putInt("lowMax", s.lowMax)
            .putInt("maxConsecutive", s.maxConsecutive)
            .apply()
    }
}
