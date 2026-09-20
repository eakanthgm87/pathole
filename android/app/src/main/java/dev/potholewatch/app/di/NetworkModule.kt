package dev.potholewatch.app.di

import com.jakewharton.retrofit2.converter.kotlinx.serialization.asConverterFactory
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import dev.potholewatch.app.BuildConfig
import dev.potholewatch.app.data.ServerConfig
import dev.potholewatch.app.data.TokenStore
import dev.potholewatch.app.data.api.PotholeApi
import dev.potholewatch.app.data.api.RefreshRequest
import dev.potholewatch.app.data.api.TokenPair
import java.util.concurrent.TimeUnit
import javax.inject.Named
import javax.inject.Singleton
import kotlinx.serialization.json.Json
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit

@Module
@InstallIn(SingletonComponent::class)
object NetworkModule {

    @Provides
    @Singleton
    fun json(): Json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
        coerceInputValues = true
    }

    /**
     * Points every request at the base URL stored on the device.
     *
     * Retrofit fixes its base URL when it is built, so changing the server
     * would otherwise need an app restart. Rewriting here means the Profile
     * screen can repoint the app live.
     */
    @Provides
    @Singleton
    @Named("server")
    fun serverInterceptor(config: ServerConfig): Interceptor = Interceptor { chain ->
        val target = config.httpUrl
        val request = chain.request()
        if (target == null) return@Interceptor chain.proceed(request)

        val rebuilt = request.url.newBuilder()
            .scheme(target.scheme)
            .host(target.host)
            .port(target.port)
            .build()
        chain.proceed(request.newBuilder().url(rebuilt).build())
    }

    /**
     * Attaches the access token and, on a 401, refreshes once and retries.
     *
     * Synchronised so a burst of parallel calls performs one refresh rather
     * than a stampede that would invalidate each other's rotated tokens.
     */
    @Provides
    @Singleton
    @Named("auth")
    fun authInterceptor(
        tokens: TokenStore,
        json: Json,
        config: ServerConfig,
    ): Interceptor = object : Interceptor {
        private val lock = Any()

        override fun intercept(chain: Interceptor.Chain): Response {
            val original = chain.request()
            if (original.url.encodedPath.contains("/auth/")) {
                return chain.proceed(original)
            }

            val first = chain.proceed(original.withToken(tokens.access))
            if (first.code != 401) return first
            first.close()

            val refreshed = synchronized(lock) { refreshToken(chain, tokens, json) }
            if (!refreshed) {
                tokens.clear()
                return chain.proceed(original)
            }
            return chain.proceed(original.withToken(tokens.access))
        }

        private fun Request.withToken(token: String?): Request =
            if (token.isNullOrBlank()) this
            else newBuilder().header("Authorization", "Bearer $token").build()

        private fun refreshToken(chain: Interceptor.Chain, tokens: TokenStore, json: Json): Boolean {
            val refresh = tokens.refresh ?: return false
            val body = okhttp3.RequestBody.create(
                "application/json".toMediaType(),
                json.encodeToString(RefreshRequest.serializer(), RefreshRequest(refresh)),
            )
            val request = Request.Builder()
                .url(config.baseUrl.value + "auth/refresh/")
                .post(body)
                .build()
            return try {
                chain.proceed(request).use { response ->
                    if (!response.isSuccessful) return false
                    val text = response.body?.string() ?: return false
                    val pair = json.decodeFromString(TokenPair.serializer(), text)
                    tokens.save(pair.access, pair.refresh)
                    true
                }
            } catch (e: Exception) {
                false
            }
        }
    }

    @Provides
    @Singleton
    fun okHttp(
        @Named("server") server: Interceptor,
        @Named("auth") auth: Interceptor,
    ): OkHttpClient = OkHttpClient.Builder()
        // Order matters: repoint the host first, then attach credentials.
        .addInterceptor(server)
        .addInterceptor(auth)
        .addInterceptor(
            HttpLoggingInterceptor().apply {
                level = if (BuildConfig.DEBUG) HttpLoggingInterceptor.Level.BASIC
                else HttpLoggingInterceptor.Level.NONE
            }
        )
        .connectTimeout(20, TimeUnit.SECONDS)
        // Inference on a CPU worker can take a few seconds per upload.
        .readTimeout(90, TimeUnit.SECONDS)
        .writeTimeout(90, TimeUnit.SECONDS)
        .build()

    @Provides
    @Singleton
    fun retrofit(client: OkHttpClient, json: Json): Retrofit = Retrofit.Builder()
        .baseUrl(BuildConfig.API_BASE)
        .client(client)
        .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
        .build()

    @Provides
    @Singleton
    fun api(retrofit: Retrofit): PotholeApi = retrofit.create(PotholeApi::class.java)
}
