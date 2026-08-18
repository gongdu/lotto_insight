package com.example.lottoinsight

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.NumberFormat
import java.util.Locale

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { MaterialTheme { App() } }
    }
}

enum class Tab(val title: String) {
    HOME("홈"), DRAWS("조회"), PREDICT("추천"), MY("내번호"), STORES("판매점"), PENSION("연금")
}

@Composable
fun App() {
    var tab by remember { mutableStateOf(Tab.HOME) }
    Scaffold(
        bottomBar = {
            NavigationBar {
                Tab.entries.forEach { t ->
                    NavigationBarItem(
                        selected = tab == t,
                        onClick = { tab = t },
                        icon = {
                            Icon(
                                when (t) {
                                    Tab.HOME -> Icons.Default.Home
                                    Tab.DRAWS -> Icons.Default.Search
                                    Tab.PREDICT -> Icons.Default.AutoAwesome
                                    Tab.MY -> Icons.Default.Bookmarks
                                    Tab.STORES -> Icons.Default.Store
                                    Tab.PENSION -> Icons.Default.ConfirmationNumber
                                }, null
                            )
                        },
                        label = { Text(t.title) }
                    )
                }
            }
        }
    ) { pad ->
        Box(Modifier.padding(pad)) {
            when (tab) {
                Tab.HOME -> Home()
                Tab.DRAWS -> Draws()
                Tab.PREDICT -> Predict()
                Tab.MY -> MyNumbers()
                Tab.STORES -> Stores()
                Tab.PENSION -> Pension()
            }
        }
    }
}

@Composable
fun rememberDb(): LotteryDb {
    val context = androidx.compose.ui.platform.LocalContext.current
    return remember(context) { LotteryDb(context) }
}

@Composable
fun Home() {
    val db = rememberDb()
    val ctx = androidx.compose.ui.platform.LocalContext.current
    val scope = rememberCoroutineScope()
    var draw by remember { mutableStateOf<LottoDraw?>(null) }
    var url by remember { mutableStateOf(SyncConfig.get(ctx)) }
    var msg by remember { mutableStateOf("") }
    var syncing by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) { draw = withContext(Dispatchers.IO) { db.latestDraw() } }

    LazyColumn(
        Modifier.fillMaxSize().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        item {
            Text("로또 인사이트", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
            Text("오프라인 조회 · 통계 분석 · 내 번호 검사 · GitHub Pages 자동 동기화")
        }
        item {
            ElevatedCard(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text("최신 로또", fontWeight = FontWeight.Bold)
                    draw?.let {
                        Text("제 ${it.round}회 · ${it.date}")
                        Balls(it.numbers)
                        Text("보너스 ${it.bonus}")
                        Text("1등 ${it.firstWinners ?: "-"}명 · ${money(it.firstPrize)}")
                    } ?: Text("데이터를 불러오는 중입니다.")
                }
            }
        }
        item {
            OutlinedTextField(
                value = url,
                onValueChange = { url = it },
                label = { Text("GitHub Pages 데이터 주소") },
                placeholder = { Text("https://사용자명.github.io/저장소명") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true
            )
            Spacer(Modifier.height(8.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = {
                    SyncConfig.set(ctx, url)
                    msg = "데이터 주소를 저장했습니다."
                }) { Text("저장") }
                OutlinedButton(
                    enabled = !syncing,
                    onClick = {
                        scope.launch {
                            syncing = true
                            msg = runCatching { withContext(Dispatchers.IO) { SyncClient(ctx).sync() } }
                                .fold({ "동기화 완료 · $it" }, { "동기화 실패: ${it.message}" })
                            draw = withContext(Dispatchers.IO) { db.latestDraw() }
                            syncing = false
                        }
                    }
                ) {
                    if (syncing) CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                    else Icon(Icons.Default.Sync, null)
                    Spacer(Modifier.width(6.dp))
                    Text("지금 동기화")
                }
            }
            if (msg.isNotBlank()) Text(msg, style = MaterialTheme.typography.bodySmall)
        }
        item {
            AssistChip(
                onClick = {},
                label = { Text("추천 점수는 과거 통계의 균형 지표이며 당첨 확률 상승을 보장하지 않습니다.") }
            )
        }
    }
}

@Composable
fun Draws() {
    var mode by remember { mutableIntStateOf(0) }
    Column(Modifier.fillMaxSize().padding(16.dp)) {
        Text("로또 조회 · 통계", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(8.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip(selected = mode == 0, onClick = { mode = 0 }, label = { Text("회차 조회") }, leadingIcon = { Icon(Icons.Default.Search, null) })
            FilterChip(selected = mode == 1, onClick = { mode = 1 }, label = { Text("번호 통계") }, leadingIcon = { Icon(Icons.Default.BarChart, null) })
        }
        Spacer(Modifier.height(8.dp))
        if (mode == 0) DrawHistory(Modifier.weight(1f)) else NumberStatsScreen(Modifier.weight(1f))
    }
}

@Composable
private fun DrawHistory(modifier: Modifier = Modifier) {
    val db = rememberDb()
    var q by remember { mutableStateOf("") }
    var rows by remember { mutableStateOf<List<LottoDraw>>(emptyList()) }
    LaunchedEffect(q) { rows = withContext(Dispatchers.IO) { db.draws(query = q) } }
    Column(modifier) {
        OutlinedTextField(
            q,
            { q = it.filter(Char::isDigit) },
            label = { Text("회차") },
            modifier = Modifier.fillMaxWidth(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
            singleLine = true
        )
        Spacer(Modifier.height(8.dp))
        LazyColumn(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(rows) { d ->
                ElevatedCard(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text("${d.round}회 · ${d.date}", fontWeight = FontWeight.Bold)
                        Balls(d.numbers)
                        Text("보너스 ${d.bonus} · 1등 ${d.firstWinners ?: "-"}명 · ${money(d.firstPrize)}")
                        if (d.auto != null || d.manual != null || d.half != null) {
                            Text("자동 ${d.auto ?: "-"} · 수동 ${d.manual ?: "-"} · 반자동 ${d.half ?: "-"}", style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun NumberStatsScreen(modifier: Modifier = Modifier) {
    val db = rememberDb()
    var window by remember { mutableIntStateOf(60) }
    var stats by remember { mutableStateOf<List<NumberStat>>(emptyList()) }
    LaunchedEffect(window) {
        val draws = withContext(Dispatchers.IO) { db.allNumbers() }
        stats = withContext(Dispatchers.Default) { Predictor.stats(draws, window) }
    }
    Column(modifier) {
        Stepper("최근 분석 회차", window, 10, 200, 10) { window = it }
        Spacer(Modifier.height(8.dp))
        LazyColumn(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item {
                ElevatedCard(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(14.dp)) {
                        Text("최근 $window 회 번호별 출현 차트", fontWeight = FontWeight.Bold)
                        Spacer(Modifier.height(8.dp))
                        FrequencyChart(stats)
                        Text("왼쪽 1번 → 오른쪽 45번", style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
            item {
                Text("최근 출현 상위", fontWeight = FontWeight.Bold)
            }
            items(stats.sortedByDescending { it.recentCount }.take(12)) { s -> StatRow(s, window) }
            item { Text("장기 미출현 상위", fontWeight = FontWeight.Bold) }
            items(stats.sortedByDescending { it.gap }.take(12)) { s -> StatRow(s, window) }
        }
    }
}

@Composable
private fun FrequencyChart(stats: List<NumberStat>) {
    val color = MaterialTheme.colorScheme.primary
    val guide = MaterialTheme.colorScheme.outlineVariant
    val max = stats.maxOfOrNull { it.recentCount }?.coerceAtLeast(1) ?: 1
    Canvas(Modifier.fillMaxWidth().height(180.dp)) {
        if (stats.isEmpty()) return@Canvas
        val barSlot = size.width / 45f
        drawLine(guide, Offset(0f, size.height), Offset(size.width, size.height), strokeWidth = 1f)
        stats.sortedBy { it.number }.forEachIndexed { index, stat ->
            val h = size.height * stat.recentCount.toFloat() / max.toFloat()
            drawRect(
                color = color,
                topLeft = Offset(index * barSlot + barSlot * 0.15f, size.height - h),
                size = Size(barSlot * 0.7f, h)
            )
        }
    }
}

@Composable
private fun StatRow(s: NumberStat, window: Int) {
    ListItem(
        headlineContent = { Text("${s.number}번", fontWeight = FontWeight.Bold) },
        supportingContent = { Text("전체 ${s.totalCount}회 · 최근 ${minOf(window, 9999)}회 ${s.recentCount}회 · 현재 ${s.gap}회 미출현") },
        trailingContent = { Text("%.1f%%".format(s.recentRate * 100)) }
    )
    HorizontalDivider()
}

@Composable
fun Predict() {
    val db = rememberDb()
    val ctx = androidx.compose.ui.platform.LocalContext.current
    val scope = rememberCoroutineScope()
    var rows by remember { mutableStateOf<List<Prediction>>(emptyList()) }
    var settings by remember { mutableStateOf(PredictionConfig.load(ctx)) }
    var msg by remember { mutableStateOf("") }
    var generating by remember { mutableStateOf(false) }

    LazyColumn(
        Modifier.fillMaxSize().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        item {
            Text("통계 기반 번호 추천", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
            Text("추천 조건을 직접 조절할 수 있습니다. 모든 유효 조합의 실제 추첨 확률은 동일합니다.")
        }
        item {
            ElevatedCard(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text("추천 조건", fontWeight = FontWeight.Bold)
                    Stepper("최근 분석 회차", settings.recentWindow, 10, 200, 10) { settings = settings.copy(recentWindow = it) }
                    Stepper("번호 합 최소", settings.sumMin, 21, 200, 5) { settings = settings.copy(sumMin = it).normalized() }
                    Stepper("번호 합 최대", settings.sumMax, 80, 255, 5) { settings = settings.copy(sumMax = it).normalized() }
                    Stepper("홀수 최소", settings.oddMin, 0, 6, 1) { settings = settings.copy(oddMin = it).normalized() }
                    Stepper("홀수 최대", settings.oddMax, 0, 6, 1) { settings = settings.copy(oddMax = it).normalized() }
                    Stepper("저번호(1~22) 최소", settings.lowMin, 0, 6, 1) { settings = settings.copy(lowMin = it).normalized() }
                    Stepper("저번호(1~22) 최대", settings.lowMax, 0, 6, 1) { settings = settings.copy(lowMax = it).normalized() }
                    Stepper("허용 연속쌍", settings.maxConsecutive, 0, 5, 1) { settings = settings.copy(maxConsecutive = it) }
                    OutlinedButton(onClick = {
                        settings = settings.normalized()
                        PredictionConfig.save(ctx, settings)
                        msg = "추천 조건을 저장했습니다."
                    }) { Icon(Icons.Default.Save, null); Spacer(Modifier.width(6.dp)); Text("조건 저장") }
                }
            }
        }
        item {
            Button(
                enabled = !generating,
                onClick = {
                    scope.launch {
                        generating = true
                        val draws = withContext(Dispatchers.IO) { db.allNumbers() }
                        rows = withContext(Dispatchers.Default) { Predictor.generate(draws, 5, settings) }
                        msg = if (rows.isEmpty()) "조건이 너무 좁습니다. 범위를 넓혀주세요." else "5게임을 생성했습니다."
                        generating = false
                    }
                }
            ) {
                Icon(Icons.Default.AutoAwesome, null)
                Spacer(Modifier.width(6.dp))
                Text("5게임 생성")
            }
            if (msg.isNotBlank()) Text(msg, style = MaterialTheme.typography.bodySmall)
        }
        items(rows) { p ->
            ElevatedCard(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Balls(p.numbers)
                    Text("균형점수 %.1f".format(p.score), fontWeight = FontWeight.Bold)
                    Text(p.description, style = MaterialTheme.typography.bodySmall)
                    OutlinedButton(onClick = {
                        scope.launch {
                            runCatching { withContext(Dispatchers.IO) { db.saveTicket(p.numbers, "추천 조합", "prediction", p.score) } }
                                .onSuccess { msg = "내 번호에 저장했습니다." }
                                .onFailure { msg = "저장 실패: ${it.message}" }
                        }
                    }) {
                        Icon(Icons.Default.BookmarkAdd, null)
                        Spacer(Modifier.width(6.dp))
                        Text("내 번호 저장")
                    }
                }
            }
        }
    }
}

@Composable
fun MyNumbers() {
    val db = rememberDb()
    val scope = rememberCoroutineScope()
    var input by remember { mutableStateOf("") }
    var memo by remember { mutableStateOf("") }
    var roundText by remember { mutableStateOf("") }
    var tickets by remember { mutableStateOf<List<SavedTicket>>(emptyList()) }
    var checks by remember { mutableStateOf<Map<Long, TicketCheck>>(emptyMap()) }
    var msg by remember { mutableStateOf("") }

    suspend fun refresh() {
        tickets = withContext(Dispatchers.IO) { db.tickets() }
        val round = roundText.toIntOrNull()
        checks = if (round == null) emptyMap() else withContext(Dispatchers.IO) {
            db.ticketChecks(round).associateBy { it.ticket.id }
        }
    }

    LaunchedEffect(Unit) {
        roundText = withContext(Dispatchers.IO) { db.latestDraw()?.round?.toString().orEmpty() }
        refresh()
    }

    Column(Modifier.fillMaxSize().padding(16.dp)) {
        Text("내 번호", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        Text("직접 입력한 번호와 추천 조합을 저장하고 과거 회차와 즉시 대조합니다.")
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(
            input,
            { input = it },
            label = { Text("번호 6개") },
            placeholder = { Text("예: 3, 8, 14, 22, 31, 44") },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true
        )
        OutlinedTextField(
            memo,
            { memo = it },
            label = { Text("메모 (선택)") },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true
        )
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = {
                val nums = parseTicketInput(input)
                scope.launch {
                    if (nums == null) {
                        msg = "1~45 사이 서로 다른 번호 6개를 입력하세요."
                    } else {
                        runCatching { withContext(Dispatchers.IO) { db.saveTicket(nums, memo, "manual") } }
                            .onSuccess {
                                input = ""
                                memo = ""
                                msg = "번호를 저장했습니다."
                                refresh()
                            }
                            .onFailure { msg = "저장 실패: ${it.message}" }
                    }
                }
            }) { Icon(Icons.Default.Add, null); Spacer(Modifier.width(4.dp)); Text("저장") }
            OutlinedTextField(
                roundText,
                { roundText = it.filter(Char::isDigit) },
                label = { Text("검사 회차") },
                modifier = Modifier.width(130.dp),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                singleLine = true
            )
            OutlinedButton(onClick = { scope.launch { refresh(); msg = if (checks.isEmpty()) "해당 회차를 찾지 못했거나 저장 번호가 없습니다." else "당첨 여부를 검사했습니다." } }) {
                Text("검사")
            }
        }
        if (msg.isNotBlank()) Text(msg, style = MaterialTheme.typography.bodySmall)
        Spacer(Modifier.height(8.dp))
        LazyColumn(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(tickets, key = { it.id }) { ticket ->
                val check = checks[ticket.id]
                ElevatedCard(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                            Text(if (ticket.source == "prediction") "추천 저장" else "직접 저장", fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                            IconButton(onClick = {
                                scope.launch {
                                    withContext(Dispatchers.IO) { db.deleteTicket(ticket.id) }
                                    refresh()
                                }
                            }) { Icon(Icons.Default.Delete, "삭제") }
                        }
                        Balls(ticket.numbers)
                        if (ticket.memo.isNotBlank()) Text(ticket.memo, style = MaterialTheme.typography.bodySmall)
                        ticket.score?.let { Text("저장 당시 균형점수 %.1f".format(it), style = MaterialTheme.typography.bodySmall) }
                        check?.let {
                            val resultColor = if (it.rank != null) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant
                            Text("${it.draw.round}회 결과: ${it.label} · 본번호 ${it.matchCount}개${if (it.bonusMatched) " + 보너스" else ""}", color = resultColor, fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun Stores() {
    val db = rememberDb()
    var q by remember { mutableStateOf("") }
    var rows by remember { mutableStateOf<List<WinningStore>>(emptyList()) }
    LaunchedEffect(q) { rows = withContext(Dispatchers.IO) { db.stores(q) } }
    Column(Modifier.fillMaxSize().padding(16.dp)) {
        Text("당첨 판매점", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        OutlinedTextField(q, { q = it }, label = { Text("판매점명 / 지역 / 주소") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
        LazyColumn(Modifier.weight(1f)) {
            items(rows) { s ->
                ListItem(
                    headlineContent = { Text(s.name, fontWeight = FontWeight.Bold) },
                    supportingContent = { Text("${s.round}회 ${s.rank}등 · ${s.region}\n${s.address}") },
                    leadingContent = { Icon(Icons.Default.Store, null) }
                )
                HorizontalDivider()
            }
        }
    }
}

@Composable
fun Pension() {
    val db = rememberDb()
    var roundText by remember { mutableStateOf("") }
    var rows by remember { mutableStateOf<List<PensionResult>>(emptyList()) }
    suspend fun load() {
        rows = withContext(Dispatchers.IO) { db.pension(roundText.toIntOrNull()) }
    }
    LaunchedEffect(Unit) { load() }
    Column(Modifier.fillMaxSize().padding(16.dp)) {
        Text("연금복권720+", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(
                roundText,
                { roundText = it.filter(Char::isDigit) },
                label = { Text("회차 (비우면 최신)") },
                modifier = Modifier.weight(1f),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                singleLine = true
            )
            val scope = rememberCoroutineScope()
            Button(onClick = { scope.launch { load() } }) { Text("조회") }
        }
        rows.firstOrNull()?.let { Text("${it.round}회 · ${it.date}") }
        LazyColumn(Modifier.weight(1f)) {
            items(rows) { r ->
                ListItem(
                    headlineContent = {
                        Text(
                            when {
                                r.rank == 1 -> "1등 ${r.rankClass}조 ${r.rankNo}"
                                r.rank == 21 -> "보너스 ${r.rankNo}"
                                else -> "${r.rank}등 ${r.rankNo}"
                            },
                            fontWeight = FontWeight.Bold
                        )
                    },
                    supportingContent = { Text("당첨금 ${money(r.amount)} · ${r.winners ?: "-"}매") }
                )
                HorizontalDivider()
            }
        }
    }
}

@Composable
fun Stepper(label: String, value: Int, min: Int, max: Int, step: Int = 1, onChange: (Int) -> Unit) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(label, modifier = Modifier.weight(1f))
        IconButton(onClick = { onChange((value - step).coerceAtLeast(min)) }, enabled = value > min) { Icon(Icons.Default.Remove, null) }
        Text(value.toString(), modifier = Modifier.widthIn(min = 38.dp), fontWeight = FontWeight.Bold)
        IconButton(onClick = { onChange((value + step).coerceAtMost(max)) }, enabled = value < max) { Icon(Icons.Default.Add, null) }
    }
}

@Composable
fun Balls(nums: List<Int>) {
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        nums.forEach { n ->
            Surface(shape = CircleShape, tonalElevation = 3.dp, modifier = Modifier.size(38.dp)) {
                Box(contentAlignment = Alignment.Center) { Text(n.toString(), fontWeight = FontWeight.Bold) }
            }
        }
    }
}

fun parseTicketInput(text: String): List<Int>? {
    val raw = Regex("\\d+").findAll(text).map { it.value.toInt() }.toList()
    if (raw.size != 6 || raw.toSet().size != 6 || raw.any { it !in 1..45 }) return null
    return raw.sorted()
}

fun money(v: Long?): String = if (v == null) "-" else NumberFormat.getNumberInstance(Locale.KOREA).format(v) + "원"
