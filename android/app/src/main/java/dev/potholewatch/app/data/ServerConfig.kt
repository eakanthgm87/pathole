package dev.potholewatch.app.data

import android.content.Context
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull

/**
 * Where the backend lives, changeable at runtime.
 *
 * The build-time default is only a default. `10.0.2.2` is the emulator's
 * alias for the host machine and is unreachable from a real phone, which is
 * the usual reason the app "cannot reach the server". Rather than require a
 * rebuild per environment, the base URL is stored on the device and can be
 * pointed at a laptop on the LAN or a deployed host from the Profile screen.
 */
@Singleton
class ServerConfig @Inject constructor(@ApplicationContext context: Context) {

    private val prefs = context.getSharedPreferences("pw_server", Context.MODE_PRIVATE)

    private val _baseUrl = MutableStateFlow(
        prefs.getString(KEY, null) ?: dev.potholewatch.app.BuildConfig.API_BASE
    )
    val baseUrl: StateFlow<String> = _baseUrl

    /** Parsed form used by the interceptor. Null only if a stored value is corrupt. */
    val httpUrl: HttpUrl?
        get() = _baseUrl.value.toHttpUrlOrNull()

    /**
     * Accepts what a person would actually type: "example.onrender.com",
     * "http://192.168.1.5:8000", "https://host/api/v1/". Returns the
     * normalised URL, or null when it cannot be made into one.
     */
    fun normalise(input: String): String? {
        var text = input.trim()
        if (text.isEmpty()) return null
        if (!text.startsWith("http://") && !text.startsWith("https://")) {
            // Plain hostnames are almost always a deployed host, so assume TLS.
            text = "https://$text"
        }
        text = text.trimEnd('/')
        if (!text.endsWith("/api/v1")) {
            text = "$text/api/v1"
        }
        val url = "$text/".toHttpUrlOrNull() ?: return null
        return url.toString()
    }

    /** Returns true when the value was valid and stored. */
    fun set(input: String): Boolean {
        val normalised = normalise(input) ?: return false
        prefs.edit().putString(KEY, normalised).apply()
        _baseUrl.value = normalised
        return true
    }

    fun reset() {
        prefs.edit().remove(KEY).apply()
        _baseUrl.value = dev.potholewatch.app.BuildConfig.API_BASE
    }

    private companion object {
        const val KEY = "base_url"
    }
}
