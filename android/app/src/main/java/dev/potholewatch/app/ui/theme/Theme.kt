package dev.potholewatch.app.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

// Mirrors the website's tokens so the two products read as one system.
val Accent = Color(0xFF5B8CFF)
val Accent2 = Color(0xFF9D6BFF)
val SevLow = Color(0xFF35D0A5)
val SevMedium = Color(0xFFF5B83D)
val SevHigh = Color(0xFFFF5A6E)

// Pure black, matching the web canvas: OLED panels switch the pixels off.
private val Ink = Color(0xFF000000)
private val Surface1 = Color(0xFF0B0B0F)
private val Surface2 = Color(0xFF14141A)
private val OnInk = Color(0xFFF4F5F7)
private val OnInkDim = Color(0xFFA8ADB8)

private val DarkColors = darkColorScheme(
    primary = Accent,
    onPrimary = Color.White,
    secondary = Accent2,
    background = Ink,
    onBackground = OnInk,
    surface = Surface1,
    onSurface = OnInk,
    surfaceVariant = Surface2,
    onSurfaceVariant = OnInkDim,
    error = SevHigh,
    outline = Color(0x1AFFFFFF),
)

private val LightColors = lightColorScheme(
    primary = Accent,
    secondary = Accent2,
    background = Color(0xFFF6F7FB),
    surface = Color.White,
    error = SevHigh,
)

private val AppShapes = Shapes(
    extraSmall = RoundedCornerShape(8.dp),
    small = RoundedCornerShape(10.dp),
    medium = RoundedCornerShape(16.dp),
    large = RoundedCornerShape(22.dp),
    extraLarge = RoundedCornerShape(28.dp),
)

private val AppTypography = Typography(
    headlineLarge = TextStyle(fontSize = 30.sp, fontWeight = FontWeight.Bold, letterSpacing = (-0.6).sp),
    headlineSmall = TextStyle(fontSize = 21.sp, fontWeight = FontWeight.SemiBold, letterSpacing = (-0.3).sp),
    titleMedium = TextStyle(fontSize = 16.sp, fontWeight = FontWeight.SemiBold),
    bodyLarge = TextStyle(fontSize = 15.sp, lineHeight = 22.sp),
    bodyMedium = TextStyle(fontSize = 13.5.sp, lineHeight = 19.sp),
    labelSmall = TextStyle(fontSize = 11.sp, fontWeight = FontWeight.Medium, letterSpacing = 0.6.sp),
)

fun severityColor(severity: String): Color = when (severity) {
    "high" -> SevHigh
    "medium" -> SevMedium
    else -> SevLow
}

@Composable
fun PotholeTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    MaterialTheme(
        colorScheme = if (darkTheme) DarkColors else LightColors,
        typography = AppTypography,
        shapes = AppShapes,
        content = content,
    )
}
