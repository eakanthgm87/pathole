package dev.potholewatch.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Map
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.PhotoCamera
import androidx.compose.material.icons.filled.List
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import dagger.hilt.android.AndroidEntryPoint
import dev.potholewatch.app.ui.AuthViewModel
import dev.potholewatch.app.ui.LoginScreen
import dev.potholewatch.app.ui.MyReportsScreen
import dev.potholewatch.app.ui.NotificationsScreen
import dev.potholewatch.app.ui.RegisterScreen
import dev.potholewatch.app.ui.components.AmbientBackground
import dev.potholewatch.app.ui.theme.PotholeTheme

private data class Tab(val route: String, val label: String, val icon: ImageVector)

private val TABS = listOf(
    Tab("map", "Map", Icons.Filled.Map),
    Tab("reports", "Reports", Icons.Filled.List),
    Tab("capture", "Report", Icons.Filled.PhotoCamera),
    Tab("alerts", "Alerts", Icons.Filled.Notifications),
    Tab("profile", "Profile", Icons.Filled.Person),
)

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            PotholeTheme(darkTheme = true) {
                AmbientBackground { Root() }
            }
        }
    }
}

@Composable
private fun Root(auth: AuthViewModel = hiltViewModel()) {
    val signedIn by auth.signedIn.collectAsState()
    val nav = rememberNavController()

    if (!signedIn) {
        NavHost(nav, startDestination = "login") {
            composable("login") { LoginScreen(onRegister = { nav.navigate("register") }) }
            composable("register") { RegisterScreen(onBack = { nav.popBackStack() }) }
        }
        return
    }

    val backStack by nav.currentBackStackEntryAsState()
    val current = backStack?.destination

    Scaffold(
        bottomBar = {
            NavigationBar {
                TABS.forEach { tab ->
                    NavigationBarItem(
                        selected = current?.hierarchy?.any { it.route == tab.route } == true,
                        onClick = {
                            nav.navigate(tab.route) {
                                popUpTo(nav.graph.findStartDestination().id) { saveState = true }
                                launchSingleTop = true
                                restoreState = true
                            }
                        },
                        icon = { Icon(tab.icon, contentDescription = tab.label) },
                        label = { Text(tab.label) },
                    )
                }
            }
        },
    ) { padding ->
        NavHost(nav, startDestination = "map") {
            composable("map") { MapScreen(padding) }
            composable("reports") { MyReportsScreen(padding) { id -> nav.navigate("report/$id") } }
            composable("capture") { CaptureScreen(padding) }
            composable("alerts") { NotificationsScreen(padding) }
            composable("profile") { ProfileScreen(padding, onSignOut = auth::signOut) }
            composable("report/{id}") { entry ->
                ReportDetailScreen(padding, entry.arguments?.getString("id").orEmpty())
            }
        }
    }
}
