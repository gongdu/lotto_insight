package com.example.lottoinsight

import kotlin.math.abs
import kotlin.random.Random

object Predictor {
    fun stats(draws: List<List<Int>>, recentWindow: Int = 60): List<NumberStat> {
        if (draws.isEmpty()) return (1..45).map { NumberStat(it, 0, 0, 0, 0.0, 0.0) }
        val total = IntArray(46)
        val recent = IntArray(46)
        val gap = IntArray(46) { draws.size }
        draws.forEachIndexed { idx, row ->
            row.forEach { n ->
                if (n in 1..45) {
                    total[n]++
                    gap[n] = draws.lastIndex - idx
                }
            }
        }
        val window = minOf(recentWindow.coerceAtLeast(1), draws.size)
        draws.takeLast(window).forEach { row -> row.forEach { n -> if (n in 1..45) recent[n]++ } }
        return (1..45).map { n ->
            NumberStat(
                number = n,
                totalCount = total[n],
                recentCount = recent[n],
                gap = gap[n],
                totalRate = total[n].toDouble() / draws.size,
                recentRate = recent[n].toDouble() / window
            )
        }
    }

    fun generate(
        draws: List<List<Int>>,
        count: Int = 5,
        settings: PredictionSettings = PredictionSettings()
    ): List<Prediction> {
        if (draws.isEmpty()) return emptyList()
        val cfg = settings.normalized()
        val stats = stats(draws, cfg.recentWindow).associateBy { it.number }
        val base = (1..45).associateWith { n ->
            val s = stats.getValue(n)
            val gapScore = minOf(s.gap, 25) / 25.0
            0.45 * s.totalRate + 0.35 * s.recentRate + 0.20 * gapScore
        }

        val seen = mutableSetOf<List<Int>>()
        val out = mutableListOf<Prediction>()
        repeat(12000) {
            if (out.size >= count * 8) return@repeat
            val chosen = mutableListOf<Int>()
            val pool = (1..45).toMutableList()
            while (chosen.size < 6) {
                val weights = pool.map { (base[it] ?: 0.0) + Random.nextDouble(0.02, 0.12) }
                val sumWeights = weights.sum().coerceAtLeast(0.0001)
                var cursor = Random.nextDouble() * sumWeights
                var pick = pool.last()
                for (i in pool.indices) {
                    cursor -= weights[i]
                    if (cursor <= 0) {
                        pick = pool[i]
                        break
                    }
                }
                chosen += pick
                pool.remove(pick)
            }

            val nums = chosen.sorted()
            if (!seen.add(nums)) return@repeat
            val odd = nums.count { it % 2 == 1 }
            val low = nums.count { it <= 22 }
            val sum = nums.sum()
            val consecutive = nums.zipWithNext().count { (a, b) -> b - a == 1 }
            if (odd !in cfg.oddMin..cfg.oddMax) return@repeat
            if (low !in cfg.lowMin..cfg.lowMax) return@repeat
            if (sum !in cfg.sumMin..cfg.sumMax) return@repeat
            if (consecutive > cfg.maxConsecutive) return@repeat

            val oddTarget = (cfg.oddMin + cfg.oddMax) / 2.0
            val lowTarget = (cfg.lowMin + cfg.lowMax) / 2.0
            val sumTarget = (cfg.sumMin + cfg.sumMax) / 2.0
            val balance = 1.0 -
                abs(odd - oddTarget) / 6.0 * 0.20 -
                abs(low - lowTarget) / 6.0 * 0.20 -
                abs(sum - sumTarget) / 255.0 * 0.25 -
                consecutive / 5.0 * 0.10
            val raw = nums.sumOf { base[it] ?: 0.0 } / 6.0
            val score = (raw * 0.62 + balance * 0.38) * 100
            out += Prediction(
                nums,
                score,
                "최근 ${cfg.recentWindow}회·전체 빈도·미출현 간격 + 홀짝/저고/합계 균형"
            )
        }
        return out.sortedByDescending { it.score }.take(count)
    }
}

object TicketMatcher {
    fun check(numbers: List<Int>, draw: LottoDraw): Triple<Int?, Int, Boolean> {
        val selected = numbers.toSet()
        val matches = draw.numbers.count { it in selected }
        val bonus = draw.bonus in selected
        val rank = when {
            matches == 6 -> 1
            matches == 5 && bonus -> 2
            matches == 5 -> 3
            matches == 4 -> 4
            matches == 3 -> 5
            else -> null
        }
        return Triple(rank, matches, bonus)
    }
}
