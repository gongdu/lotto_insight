package com.example.lottoinsight

data class LottoDraw(
    val round: Int,
    val date: String,
    val numbers: List<Int>,
    val bonus: Int,
    val firstPrize: Long?,
    val firstWinners: Int?,
    val auto: Int?,
    val manual: Int?,
    val half: Int?
)

data class WinningStore(
    val round: Int,
    val rank: Int,
    val name: String,
    val region: String,
    val address: String,
    val autoPossible: String
)

data class PensionResult(
    val round: Int,
    val rank: Int,
    val rankClass: String,
    val rankNo: String,
    val amount: Long?,
    val winners: Int?,
    val date: String
)

data class Prediction(
    val numbers: List<Int>,
    val score: Double,
    val description: String
)

data class PredictionSettings(
    val recentWindow: Int = 60,
    val sumMin: Int = 100,
    val sumMax: Int = 180,
    val oddMin: Int = 2,
    val oddMax: Int = 4,
    val lowMin: Int = 2,
    val lowMax: Int = 4,
    val maxConsecutive: Int = 2
) {
    fun normalized(): PredictionSettings {
        val rw = recentWindow.coerceIn(10, 200)
        val s1 = sumMin.coerceIn(21, 255)
        val s2 = sumMax.coerceIn(21, 255)
        val o1 = oddMin.coerceIn(0, 6)
        val o2 = oddMax.coerceIn(0, 6)
        val l1 = lowMin.coerceIn(0, 6)
        val l2 = lowMax.coerceIn(0, 6)
        return copy(
            recentWindow = rw,
            sumMin = minOf(s1, s2),
            sumMax = maxOf(s1, s2),
            oddMin = minOf(o1, o2),
            oddMax = maxOf(o1, o2),
            lowMin = minOf(l1, l2),
            lowMax = maxOf(l1, l2),
            maxConsecutive = maxConsecutive.coerceIn(0, 5)
        )
    }
}

data class NumberStat(
    val number: Int,
    val totalCount: Int,
    val recentCount: Int,
    val gap: Int,
    val totalRate: Double,
    val recentRate: Double
)

data class SavedTicket(
    val id: Long,
    val numbers: List<Int>,
    val createdAt: String,
    val memo: String,
    val source: String,
    val score: Double?
)

data class TicketCheck(
    val ticket: SavedTicket,
    val draw: LottoDraw,
    val rank: Int?,
    val matchCount: Int,
    val bonusMatched: Boolean
) {
    val label: String get() = rank?.let { "${it}등" } ?: "미당첨"
}

data class SyncSummary(
    val lottoDraws: Int = 0,
    val lottoStores: Int = 0,
    val pensionRows: Int = 0,
    val pensionStores: Int = 0
) {
    val total: Int get() = lottoDraws + lottoStores + pensionRows + pensionStores
    override fun toString(): String =
        "로또 ${lottoDraws}건 · 판매점 ${lottoStores}건 · 연금 ${pensionRows}건 · 연금판매점 ${pensionStores}건"
}
