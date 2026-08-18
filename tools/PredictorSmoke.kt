import com.example.lottoinsight.*

fun main() {
    val draws = (1..120).map { i -> listOf(
        ((i + 1) % 45) + 1,
        ((i + 7) % 45) + 1,
        ((i + 13) % 45) + 1,
        ((i + 19) % 45) + 1,
        ((i + 25) % 45) + 1,
        ((i + 31) % 45) + 1
    ).distinct().let { if (it.size == 6) it else listOf(1,8,15,22,29,36) } }
    val stats = Predictor.stats(draws, 60)
    check(stats.size == 45)
    val picks = Predictor.generate(draws, 5, PredictionSettings())
    check(picks.size == 5)
    check(picks.all { it.numbers.size == 6 && it.numbers.distinct().size == 6 })
    val draw = LottoDraw(1, "", listOf(1,2,3,4,5,6), 7, null, null, null, null, null)
    val first = TicketMatcher.check(listOf(1,2,3,4,5,6), draw)
    val second = TicketMatcher.check(listOf(1,2,3,4,5,7), draw)
    check(first.first == 1)
    check(second.first == 2)
    println("Predictor smoke: ok; picks=" + picks.joinToString { it.numbers.toString() })
}
