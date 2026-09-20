package dev.potholewatch.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import coil.compose.AsyncImage
import dagger.hilt.android.lifecycle.HiltViewModel
import dev.potholewatch.app.data.api.NotificationDto
import dev.potholewatch.app.data.api.ReportDto
import dev.potholewatch.app.data.api.PotholeApi
import dev.potholewatch.app.data.repo.AuthRepository
import dev.potholewatch.app.data.repo.ReportRepository
import dev.potholewatch.app.ui.components.EmptyState
import dev.potholewatch.app.ui.components.GlassCard
import dev.potholewatch.app.ui.components.Loading
import dev.potholewatch.app.ui.components.SeverityChip
import dev.potholewatch.app.ui.components.StatusChip
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

// --- auth -----------------------------------------------------------------

@HiltViewModel
class AuthViewModel @Inject constructor(private val auth: AuthRepository) : ViewModel() {
    val signedIn: StateFlow<Boolean> = auth.signedIn

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error

    private val _busy = MutableStateFlow(false)
    val busy: StateFlow<Boolean> = _busy

    fun login(email: String, password: String) = viewModelScope.launch {
        _busy.value = true
        _error.value = null
        runCatching { auth.login(email, password) }
            .onFailure { _error.value = it.friendly() }
        _busy.value = false
    }

    fun register(email: String, password: String, name: String) = viewModelScope.launch {
        _busy.value = true
        _error.value = null
        runCatching { auth.register(email, password, name, "") }
            .onFailure { _error.value = it.friendly() }
        _busy.value = false
    }

    fun signOut() = auth.signOut()

    private fun Throwable.friendly(): String = when {
        message?.contains("401") == true -> "Wrong email or password."
        message?.contains("Unable to resolve host") == true -> "No connection."
        else -> message ?: "Something went wrong."
    }
}

@Composable
fun LoginScreen(vm: AuthViewModel = hiltViewModel(), onRegister: () -> Unit) {
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    val error by vm.error.collectAsState()
    val busy by vm.busy.collectAsState()

    Box(Modifier.fillMaxSize().padding(24.dp), contentAlignment = Alignment.Center) {
        GlassCard {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("Welcome back", style = MaterialTheme.typography.headlineSmall)
                OutlinedTextField(
                    value = email,
                    onValueChange = { email = it },
                    label = { Text("Email") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = password,
                    onValueChange = { password = it },
                    label = { Text("Password") },
                    singleLine = true,
                    visualTransformation = PasswordVisualTransformation(),
                    modifier = Modifier.fillMaxWidth(),
                )
                error?.let {
                    Text(it, color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodyMedium)
                }
                Button(
                    onClick = { vm.login(email, password) },
                    enabled = !busy && email.isNotBlank() && password.isNotBlank(),
                    modifier = Modifier.fillMaxWidth(),
                ) { Text(if (busy) "Signing in…" else "Sign in") }
                TextButton(onClick = onRegister, modifier = Modifier.fillMaxWidth()) {
                    Text("Create an account")
                }
            }
        }
    }
}

@Composable
fun RegisterScreen(vm: AuthViewModel = hiltViewModel(), onBack: () -> Unit) {
    var name by remember { mutableStateOf("") }
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    val error by vm.error.collectAsState()
    val busy by vm.busy.collectAsState()

    Box(Modifier.fillMaxSize().padding(24.dp), contentAlignment = Alignment.Center) {
        GlassCard {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("Create your account", style = MaterialTheme.typography.headlineSmall)
                OutlinedTextField(value = name, onValueChange = { name = it },
                    label = { Text("Full name") }, singleLine = true,
                    modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = email, onValueChange = { email = it },
                    label = { Text("Email") }, singleLine = true,
                    modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = password, onValueChange = { password = it },
                    label = { Text("Password (8+ characters)") }, singleLine = true,
                    visualTransformation = PasswordVisualTransformation(),
                    modifier = Modifier.fillMaxWidth())
                error?.let {
                    Text(it, color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodyMedium)
                }
                Button(
                    onClick = { vm.register(email, password, name) },
                    enabled = !busy && email.isNotBlank() && password.length >= 8,
                    modifier = Modifier.fillMaxWidth(),
                ) { Text(if (busy) "Creating…" else "Create account") }
                TextButton(onClick = onBack, modifier = Modifier.fillMaxWidth()) {
                    Text("I already have an account")
                }
            }
        }
    }
}

// --- my reports -----------------------------------------------------------

@HiltViewModel
class ReportsViewModel @Inject constructor(
    private val repo: ReportRepository,
) : ViewModel() {

    private val _reports = MutableStateFlow<List<ReportDto>?>(null)
    val reports: StateFlow<List<ReportDto>?> = _reports

    val pendingCount = repo.pendingCount

    fun load() = viewModelScope.launch {
        runCatching { repo.myReports() }
            .onSuccess { _reports.value = it.results }
            .onFailure { _reports.value = emptyList() }
    }
}

@Composable
fun MyReportsScreen(
    padding: PaddingValues,
    vm: ReportsViewModel = hiltViewModel(),
    onOpen: (String) -> Unit,
) {
    val reports by vm.reports.collectAsState()
    val pending by vm.pendingCount.collectAsState(initial = 0)
    LaunchedEffect(Unit) { vm.load() }

    Column(Modifier.fillMaxSize().padding(padding)) {
        if (pending > 0) {
            GlassCard(Modifier.padding(16.dp).fillMaxWidth()) {
                Text("$pending report${if (pending == 1) "" else "s"} waiting to upload",
                    style = MaterialTheme.typography.bodyMedium)
            }
        }
        when (val list = reports) {
            null -> Loading()
            else -> if (list.isEmpty()) {
                EmptyState("🕳️", "No reports yet. Tap the camera to make your first one.")
            } else {
                LazyColumn(
                    contentPadding = PaddingValues(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    items(list, key = { it.id }) { report ->
                        ReportRow(report) { onOpen(report.id) }
                    }
                }
            }
        }
    }
}

@Composable
private fun ReportRow(report: ReportDto, onClick: () -> Unit) {
    GlassCard(Modifier.fillMaxWidth()) {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            if (report.thumbnail.isNotBlank()) {
                AsyncImage(
                    model = report.thumbnail,
                    contentDescription = null,
                    modifier = Modifier.fillMaxWidth().height(150.dp),
                )
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                SeverityChip(report.severity)
                StatusChip(report.workflowStatus)
            }
            Text(
                report.address.ifBlank { "Location pending" },
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            TextButton(onClick = onClick) { Text("View details") }
        }
    }
}

// --- notifications --------------------------------------------------------

@HiltViewModel
class NotificationsViewModel @Inject constructor(private val api: PotholeApi) : ViewModel() {
    private val _items = MutableStateFlow<List<NotificationDto>?>(null)
    val items: StateFlow<List<NotificationDto>?> = _items

    fun load() = viewModelScope.launch {
        runCatching { api.notifications() }
            .onSuccess { _items.value = it.results }
            .onFailure { _items.value = emptyList() }
    }

    fun markRead(id: Int) = viewModelScope.launch {
        runCatching { api.markRead(id) }
        load()
    }
}

@Composable
fun NotificationsScreen(
    padding: PaddingValues,
    vm: NotificationsViewModel = hiltViewModel(),
) {
    val items by vm.items.collectAsState()
    LaunchedEffect(Unit) { vm.load() }

    when (val list = items) {
        null -> Loading(Modifier.padding(padding))
        else -> if (list.isEmpty()) {
            Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                EmptyState("🔔", "No alerts yet.")
            }
        } else {
            LazyColumn(
                contentPadding = PaddingValues(16.dp),
                modifier = Modifier.padding(padding),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                items(list, key = { it.id }) { note ->
                    GlassCard(Modifier.fillMaxWidth()) {
                        Text(note.title, style = MaterialTheme.typography.titleMedium)
                        if (note.body.isNotBlank()) {
                            Text(note.body, style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        if (!note.isRead) {
                            TextButton(onClick = { vm.markRead(note.id) }) { Text("Mark read") }
                        }
                    }
                }
            }
        }
    }
}
