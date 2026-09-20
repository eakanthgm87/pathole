package dev.potholewatch.app

import android.Manifest
import android.annotation.SuppressLint
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.ImageCapture
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.with
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.MyLocation
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import coil.compose.AsyncImage
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import dagger.hilt.android.lifecycle.HiltViewModel
import dev.potholewatch.app.data.api.ReportDto
import dev.potholewatch.app.data.repo.ReportRepository
import dev.potholewatch.app.data.repo.SubmitResult
import dev.potholewatch.app.ui.components.GlassCard
import dev.potholewatch.app.ui.components.Loading
import dev.potholewatch.app.ui.components.MapPoint
import dev.potholewatch.app.ui.components.OpenLayersController
import dev.potholewatch.app.ui.components.OpenLayersMap
import dev.potholewatch.app.ui.components.RevealIn
import dev.potholewatch.app.ui.components.SeverityChip
import dev.potholewatch.app.ui.components.StatusChip
import dev.potholewatch.app.ui.screens.CAMERA_PERMISSIONS
import dev.potholewatch.app.ui.screens.CameraPreview
import dev.potholewatch.app.ui.screens.PermissionRationale
import dev.potholewatch.app.ui.screens.captureToFile
import java.io.File
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.tasks.await

// --- map ------------------------------------------------------------------

@HiltViewModel
class MapViewModel @Inject constructor(private val repo: ReportRepository) : ViewModel() {
    private val _nearby = MutableStateFlow<List<ReportDto>>(emptyList())
    val nearby: StateFlow<List<ReportDto>> = _nearby

    fun load(lat: Double, lng: Double) = viewModelScope.launch {
        runCatching { repo.nearby(lat, lng, 6000.0) }.onSuccess { _nearby.value = it }
    }
}

/**
 * OpenLayers in a WebView, sharing the website's basemap and cluster styling.
 * Keeping one map implementation across web and mobile means a change to the
 * marker language happens once.
 */
@SuppressLint("MissingPermission")
@Composable
fun MapScreen(padding: PaddingValues, vm: MapViewModel = hiltViewModel()) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val reports by vm.nearby.collectAsState()
    val controller = remember { OpenLayersController() }
    var centred by remember { mutableStateOf(false) }

    val hasLocation = ContextCompat.checkSelfPermission(
        context, Manifest.permission.ACCESS_FINE_LOCATION
    ) == android.content.pm.PackageManager.PERMISSION_GRANTED

    suspend fun locate(animate: Boolean) {
        if (!hasLocation) return
        val fix = runCatching {
            LocationServices.getFusedLocationProviderClient(context)
                .getCurrentLocation(Priority.PRIORITY_BALANCED_POWER_ACCURACY, null)
                .await()
        }.getOrNull() ?: return
        controller.setMe(fix.latitude, fix.longitude, fix.accuracy)
        if (animate) controller.setCenter(fix.latitude, fix.longitude, 15.0)
        vm.load(fix.latitude, fix.longitude)
    }

    LaunchedEffect(hasLocation) {
        if (!centred) {
            centred = true
            locate(animate = true)
            // Show something even without a fix.
            if (!hasLocation) vm.load(12.9716, 77.5946)
        }
    }

    LaunchedEffect(reports) {
        controller.setReports(
            reports.map {
                MapPoint(it.id, it.location.lat, it.location.lng, it.severity, it.workflowStatus)
            }
        )
    }

    Box(Modifier.fillMaxSize().padding(padding)) {
        OpenLayersMap(
            controller = controller,
            modifier = Modifier.fillMaxSize(),
        )

        FloatingActionButton(
            onClick = { scope.launch { locate(animate = true) } },
            modifier = Modifier.align(Alignment.BottomEnd).padding(18.dp),
            containerColor = MaterialTheme.colorScheme.surface,
        ) {
            Icon(Icons.Filled.MyLocation, contentDescription = "Locate me")
        }

        AnimatedVisibility(
            visible = reports.isEmpty(),
            enter = fadeIn() + slideInVertically { it / 2 },
            exit = fadeOut(),
            modifier = Modifier.align(Alignment.BottomCenter).padding(bottom = 18.dp),
        ) {
            GlassCard(Modifier.padding(horizontal = 16.dp)) {
                Text(
                    "No confirmed potholes nearby.",
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
        }
    }
}

// --- capture --------------------------------------------------------------

@HiltViewModel
class CaptureViewModel @Inject constructor(private val repo: ReportRepository) : ViewModel() {
    private val _state = MutableStateFlow<CaptureState>(CaptureState.Idle)
    val state: StateFlow<CaptureState> = _state

    fun submit(file: File, lat: Double, lng: Double, accuracy: Double?, notes: String) =
        viewModelScope.launch {
            _state.value = CaptureState.Uploading
            _state.value = when (val result = repo.submit(file, lat, lng, accuracy, notes)) {
                is SubmitResult.Uploaded -> CaptureState.Done(result.report)
                is SubmitResult.Queued -> CaptureState.Queued
            }
        }

    fun fail(message: String) { _state.value = CaptureState.Error(message) }

    fun reset() { _state.value = CaptureState.Idle }
}

sealed interface CaptureState {
    data object Idle : CaptureState
    data object Uploading : CaptureState
    data object Queued : CaptureState
    data class Done(val report: ReportDto) : CaptureState
    data class Error(val message: String) : CaptureState
}

@SuppressLint("MissingPermission")
@Composable
fun CaptureScreen(padding: PaddingValues, vm: CaptureViewModel = hiltViewModel()) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val state by vm.state.collectAsState()

    var granted by remember {
        mutableStateOf(
            CAMERA_PERMISSIONS.all {
                ContextCompat.checkSelfPermission(context, it) ==
                    android.content.pm.PackageManager.PERMISSION_GRANTED
            }
        )
    }
    val launcher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { result -> granted = result.values.all { it } }

    var capture by remember { mutableStateOf<ImageCapture?>(null) }
    var shot by remember { mutableStateOf<File?>(null) }
    var notes by remember { mutableStateOf("") }

    if (!granted) {
        PermissionRationale(
            onRequest = { launcher.launch(CAMERA_PERMISSIONS) },
            modifier = Modifier.padding(padding),
        )
        return
    }

    when (val s = state) {
        is CaptureState.Done -> {
            RevealIn { ResultPanel(s.report, padding) { shot = null; vm.reset() } }
            return
        }
        CaptureState.Queued -> {
            RevealIn {
                InfoPanel(
                    padding,
                    "Saved offline",
                    "No connection right now. This report uploads by itself once you are back " +
                        "online, and cannot turn into a duplicate.",
                ) { shot = null; vm.reset() }
            }
            return
        }
        is CaptureState.Error -> {
            RevealIn { InfoPanel(padding, "Could not submit", s.message) { vm.reset() } }
            return
        }
        else -> Unit
    }

    Column(
        Modifier.fillMaxSize().padding(padding).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        val file = shot
        if (file == null) {
            CameraPreview(
                modifier = Modifier.fillMaxWidth().aspectRatio(3f / 4f),
                onCaptureReady = { capture = it },
            )
            ShutterButton(
                enabled = capture != null,
                onClick = {
                    scope.launch {
                        runCatching { capture?.captureToFile(context) }
                            .onSuccess { shot = it }
                            .onFailure { vm.fail(it.message ?: "The camera failed.") }
                    }
                },
            )
        } else {
            RevealIn {
                AsyncImage(
                    model = file,
                    contentDescription = "Captured pothole",
                    modifier = Modifier.fillMaxWidth().aspectRatio(3f / 4f),
                )
            }
            OutlinedTextField(
                value = notes,
                onValueChange = { notes = it },
                label = { Text("Notes (optional)") },
                modifier = Modifier.fillMaxWidth(),
            )
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedButton(onClick = { shot = null }, modifier = Modifier.weight(1f)) {
                    Text("Retake")
                }
                Button(
                    onClick = {
                        scope.launch {
                            val fix = runCatching {
                                LocationServices.getFusedLocationProviderClient(context)
                                    .getCurrentLocation(Priority.PRIORITY_HIGH_ACCURACY, null)
                                    .await()
                            }.getOrNull()
                            if (fix == null) {
                                vm.fail("Could not get a GPS fix. Move somewhere with sky view.")
                                return@launch
                            }
                            vm.submit(
                                file, fix.latitude, fix.longitude, fix.accuracy.toDouble(), notes
                            )
                        }
                    },
                    enabled = state !is CaptureState.Uploading,
                    modifier = Modifier.weight(1f),
                ) {
                    if (state is CaptureState.Uploading) {
                        CircularProgressIndicator(
                            Modifier.size(16.dp),
                            strokeWidth = 2.dp,
                            color = MaterialTheme.colorScheme.onPrimary,
                        )
                    } else {
                        Text("Submit")
                    }
                }
            }
        }
    }
}

/** Camera shutter with a slow breathing ring, so the control reads as live. */
@Composable
private fun ShutterButton(enabled: Boolean, onClick: () -> Unit) {
    val pulse = rememberInfiniteTransition(label = "shutter")
    val scale by pulse.animateFloat(
        initialValue = 1f,
        targetValue = 1.045f,
        animationSpec = infiniteRepeatable(
            animation = tween(1600, easing = FastOutSlowInEasing),
            repeatMode = RepeatMode.Reverse,
        ),
        label = "shutter-scale",
    )
    Button(
        onClick = onClick,
        enabled = enabled,
        modifier = Modifier.fillMaxWidth().scale(if (enabled) scale else 1f),
    ) { Text("Capture") }
}

@Composable
private fun InfoPanel(
    padding: PaddingValues,
    title: String,
    body: String,
    onDismiss: () -> Unit,
) {
    Box(Modifier.fillMaxSize().padding(padding).padding(20.dp), contentAlignment = Alignment.Center) {
        GlassCard {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(title, style = MaterialTheme.typography.headlineSmall)
                Text(
                    body,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Button(onClick = onDismiss, modifier = Modifier.fillMaxWidth()) {
                    Text("Report another")
                }
            }
        }
    }
}

@Composable
private fun ResultPanel(report: ReportDto, padding: PaddingValues, onAgain: () -> Unit) {
    Column(
        Modifier.fillMaxSize().padding(padding).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        GlassCard(Modifier.fillMaxWidth()) {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(
                    when (report.detectionStatus) {
                        "pothole_detected" -> "Pothole confirmed"
                        "needs_review" -> "Sent for review"
                        "intact" -> "No pothole found"
                        else -> "Saved"
                    },
                    style = MaterialTheme.typography.headlineSmall,
                )
                if (report.image.isNotBlank()) {
                    AsyncImage(
                        model = report.image,
                        contentDescription = null,
                        modifier = Modifier.fillMaxWidth().height(220.dp),
                    )
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    SeverityChip(report.severity)
                    StatusChip(report.workflowStatus)
                }
                Text(
                    "Confidence ${"%.0f".format(report.confidence * 100)}% · " +
                        "${report.detections.size} box(es)",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Button(onClick = onAgain, modifier = Modifier.fillMaxWidth()) {
                    Text("Report another")
                }
            }
        }
    }
}

// --- detail & profile -----------------------------------------------------

@HiltViewModel
class DetailViewModel @Inject constructor(private val repo: ReportRepository) : ViewModel() {
    private val _report = MutableStateFlow<ReportDto?>(null)
    val report: StateFlow<ReportDto?> = _report

    fun load(id: String) = viewModelScope.launch {
        runCatching { repo.report(id) }.onSuccess { _report.value = it }
    }
}

@Composable
fun ReportDetailScreen(
    padding: PaddingValues,
    id: String,
    vm: DetailViewModel = hiltViewModel(),
) {
    val report by vm.report.collectAsState()
    val controller = remember { OpenLayersController() }
    LaunchedEffect(id) { vm.load(id) }

    when (val r = report) {
        null -> Loading(Modifier.padding(padding))
        else -> {
            LaunchedEffect(r.id) {
                controller.setReports(
                    listOf(
                        MapPoint(r.id, r.location.lat, r.location.lng, r.severity, r.workflowStatus)
                    )
                )
                controller.setCenter(r.location.lat, r.location.lng, 17.0)
            }
            RevealIn {
                Column(
                    Modifier.fillMaxSize().padding(padding).padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    if (r.image.isNotBlank()) {
                        AsyncImage(
                            model = r.image,
                            contentDescription = null,
                            modifier = Modifier.fillMaxWidth().height(230.dp),
                        )
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        SeverityChip(r.severity)
                        StatusChip(r.workflowStatus)
                    }
                    GlassCard(Modifier.fillMaxWidth()) {
                        Text(
                            r.address.ifBlank { "Location pending" },
                            style = MaterialTheme.typography.bodyMedium,
                        )
                        Text(
                            "Confidence ${"%.2f".format(r.confidence)} · " +
                                "severity score ${r.severityScore}",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        if (r.reportCount > 1) {
                            Text(
                                "Reported ${r.reportCount} times",
                                style = MaterialTheme.typography.bodyMedium,
                            )
                        }
                    }
                    OpenLayersMap(
                        controller = controller,
                        modifier = Modifier.fillMaxWidth().height(200.dp),
                    )
                }
            }
        }
    }
}

@HiltViewModel
class ServerViewModel @Inject constructor(
    private val config: dev.potholewatch.app.data.ServerConfig,
    private val api: dev.potholewatch.app.data.api.PotholeApi,
) : ViewModel() {
    val baseUrl = config.baseUrl

    private val _status = MutableStateFlow<String?>(null)
    val status: StateFlow<String?> = _status

    private val _busy = MutableStateFlow(false)
    val busy: StateFlow<Boolean> = _busy

    fun save(input: String) {
        _status.value = if (config.set(input)) null else "That does not look like a server address."
    }

    fun reset() {
        config.reset()
        _status.value = null
    }

    /** Hit /health/ so the person sees whether it worked, not a silent failure. */
    fun test() = viewModelScope.launch {
        _busy.value = true
        _status.value = runCatching { api.health() }
            .fold(
                onSuccess = { "Connected. Model: ${it.weights.ifBlank { "unknown" }}" },
                onFailure = { "Could not reach ${config.baseUrl.value} - ${it.message ?: "no response"}" },
            )
        _busy.value = false
    }
}

@Composable
fun ProfileScreen(
    padding: PaddingValues,
    onSignOut: () -> Unit,
    vm: ServerViewModel = hiltViewModel(),
) {
    val base by vm.baseUrl.collectAsState()
    val status by vm.status.collectAsState()
    val busy by vm.busy.collectAsState()
    var draft by remember(base) { mutableStateOf(base) }

    RevealIn {
        Column(
            Modifier.fillMaxSize().padding(padding).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            GlassCard(Modifier.fillMaxWidth()) {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text("Server", style = MaterialTheme.typography.headlineSmall)
                    Text(
                        "Where this app sends reports. The built-in default only works on an " +
                            "emulator; point it at your deployment or your machine's LAN address.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    OutlinedTextField(
                        value = draft,
                        onValueChange = { draft = it },
                        label = { Text("Server address") },
                        placeholder = { Text("potholewatch.onrender.com") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Button(
                            onClick = { vm.save(draft); vm.test() },
                            enabled = !busy,
                            modifier = Modifier.weight(1f),
                        ) { Text(if (busy) "Testing..." else "Save & test") }
                        OutlinedButton(
                            onClick = { vm.reset() },
                            modifier = Modifier.weight(1f),
                        ) { Text("Reset") }
                    }
                    status?.let {
                        Text(
                            it,
                            style = MaterialTheme.typography.bodyMedium,
                            color = if (it.startsWith("Connected"))
                                dev.potholewatch.app.ui.theme.SevLow
                            else MaterialTheme.colorScheme.error,
                        )
                    }
                }
            }

            GlassCard(Modifier.fillMaxWidth()) {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text("Account", style = MaterialTheme.typography.headlineSmall)
                    Text(
                        "Reports you submit appear on the public map, but your name and email " +
                            "never do.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    OutlinedButton(onClick = onSignOut, modifier = Modifier.fillMaxWidth()) {
                        Text("Sign out")
                    }
                }
            }
        }
    }
}
