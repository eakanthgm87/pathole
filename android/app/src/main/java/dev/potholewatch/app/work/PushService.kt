package dev.potholewatch.app.work

import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import dagger.hilt.android.AndroidEntryPoint
import dev.potholewatch.app.data.api.DeviceRequest
import dev.potholewatch.app.data.api.PotholeApi
import javax.inject.Inject
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

@AndroidEntryPoint
class PushService : FirebaseMessagingService() {

    @Inject lateinit var api: PotholeApi

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    override fun onNewToken(token: String) {
        // Registering can fail while signed out; the app re-registers on login.
        scope.launch { runCatching { api.registerDevice(DeviceRequest(token)) } }
    }

    override fun onMessageReceived(message: RemoteMessage) {
        // Notifications are rendered by the system when the payload carries a
        // notification block; data-only messages would be handled here.
    }
}
