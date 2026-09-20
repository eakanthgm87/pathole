package dev.potholewatch.app.ui.components

import android.annotation.SuppressLint
import android.graphics.Color
import android.webkit.JavascriptInterface
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import org.json.JSONArray
import org.json.JSONObject

/** One marker on the map. Kept deliberately small: the WebView only needs
 *  enough to draw and identify a point. */
data class MapPoint(
    val id: String,
    val lat: Double,
    val lng: Double,
    val severity: String,
    val status: String,
)

/** Handle for driving the map from Compose. */
class OpenLayersController {
    internal var webView: WebView? = null
    internal var ready = false
    private val queued = mutableListOf<String>()

    private fun run(js: String) {
        val view = webView
        if (view == null || !ready) {
            // The page may not have finished loading; replay once it signals ready.
            queued += js
            return
        }
        view.post { view.evaluateJavascript(js, null) }
    }

    internal fun flush() {
        ready = true
        queued.forEach { js -> webView?.post { webView?.evaluateJavascript(js, null) } }
        queued.clear()
    }

    fun setReports(points: List<MapPoint>) {
        val array = JSONArray()
        points.forEach { p ->
            array.put(
                JSONObject()
                    .put("id", p.id)
                    .put("lat", p.lat)
                    .put("lng", p.lng)
                    .put("severity", p.severity)
                    .put("status", p.status)
            )
        }
        // JSONObject.quote produces a correctly escaped JS string literal.
        run("window.PW.setReports(${JSONObject.quote(array.toString())});")
    }

    fun setCenter(lat: Double, lng: Double, zoom: Double? = null) =
        run("window.PW.setCenter($lat, $lng, ${zoom ?: "null"});")

    fun setMe(lat: Double, lng: Double, accuracy: Float?) =
        run("window.PW.setMe($lat, $lng, ${accuracy ?: 0f});")

    fun setPickMode(on: Boolean) = run("window.PW.setPickMode($on);")

    fun setPick(lat: Double, lng: Double) = run("window.PW.setPick($lat, $lng);")

    fun fitAll() = run("window.PW.fitAll();")
}

/**
 * OpenLayers in a WebView.
 *
 * The same library, basemap and cluster styling as the website, so the two
 * products render identically instead of drifting apart. Everything but the
 * tiles is served from file:///android_asset.
 */
@SuppressLint("SetJavaScriptEnabled")
@Composable
fun OpenLayersMap(
    controller: OpenLayersController,
    modifier: Modifier = Modifier,
    onMarkerClick: (String) -> Unit = {},
    onPick: (Double, Double) -> Unit = { _, _ -> },
) {
    AndroidView(
        modifier = modifier,
        factory = { context ->
            WebView(context).apply {
                setBackgroundColor(Color.BLACK)
                settings.apply {
                    javaScriptEnabled = true
                    domStorageEnabled = true
                    // Tiles are https; the page itself is a local asset.
                    allowFileAccess = false
                    allowContentAccess = false
                    builtInZoomControls = false
                    displayZoomControls = false
                    setGeolocationEnabled(false)
                }
                webViewClient = object : WebViewClient() {
                    override fun onPageFinished(view: WebView?, url: String?) {
                        controller.flush()
                    }
                }
                addJavascriptInterface(
                    object {
                        @JavascriptInterface
                        fun onReady() = controller.flush()

                        @JavascriptInterface
                        fun onMarker(id: String) = post { onMarkerClick(id) }

                        @JavascriptInterface
                        fun onPick(lat: Double, lng: Double) = post { onPick(lat, lng) }
                    },
                    "Android",
                )
                controller.webView = this
                loadUrl("file:///android_asset/map/index.html")
            }
        },
    )

    DisposableEffect(Unit) {
        onDispose {
            controller.webView?.destroy()
            controller.webView = null
            controller.ready = false
        }
    }
}
