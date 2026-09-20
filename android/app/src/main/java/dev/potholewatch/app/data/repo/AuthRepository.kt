package dev.potholewatch.app.data.repo

import dev.potholewatch.app.data.TokenStore
import dev.potholewatch.app.data.api.LoginRequest
import dev.potholewatch.app.data.api.PotholeApi
import dev.potholewatch.app.data.api.RegisterRequest
import dev.potholewatch.app.data.api.UserDto
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.StateFlow

@Singleton
class AuthRepository @Inject constructor(
    private val api: PotholeApi,
    private val tokens: TokenStore,
) {
    val signedIn: StateFlow<Boolean> = tokens.signedIn

    suspend fun login(email: String, password: String) {
        val pair = api.login(LoginRequest(email.trim().lowercase(), password))
        tokens.save(pair.access, pair.refresh)
    }

    suspend fun register(email: String, password: String, name: String, phone: String) {
        api.register(RegisterRequest(email.trim().lowercase(), password, name, phone))
        login(email, password)
    }

    suspend fun me(): UserDto = api.me()

    fun signOut() = tokens.clear()
}
