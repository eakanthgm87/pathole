package dev.potholewatch.app.data.api

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import okhttp3.MultipartBody
import okhttp3.RequestBody
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.Part
import retrofit2.http.Path
import retrofit2.http.Query

// --- wire models ----------------------------------------------------------

@Serializable
data class LatLng(val lat: Double, val lng: Double)

@Serializable
data class Detection(
    @SerialName("class") val label: String,
    val conf: Double,
    val bbox: List<Int>,
)

@Serializable
data class ReportDto(
    val id: String,
    val location: LatLng,
    val address: String = "",
    val image: String = "",
    val thumbnail: String = "",
    @SerialName("detection_status") val detectionStatus: String,
    val confidence: Double = 0.0,
    val severity: String = "low",
    @SerialName("severity_score") val severityScore: Double = 0.0,
    val detections: List<Detection> = emptyList(),
    @SerialName("workflow_status") val workflowStatus: String = "submitted",
    @SerialName("duplicate_of") val duplicateOf: String? = null,
    @SerialName("report_count") val reportCount: Int = 1,
    val notes: String = "",
    @SerialName("created_at") val createdAt: String = "",
    @SerialName("distance_m") val distanceM: Double? = null,
)

@Serializable
data class ReportEnvelope(val report: ReportDto)

@Serializable
data class Page<T>(
    val count: Int = 0,
    val next: String? = null,
    val previous: String? = null,
    val results: List<T> = emptyList(),
)

@Serializable
data class TokenPair(val access: String, val refresh: String)

@Serializable
data class RefreshRequest(val refresh: String)

@Serializable
data class LoginRequest(val email: String, val password: String)

@Serializable
data class RegisterRequest(
    val email: String,
    val password: String,
    val name: String = "",
    val phone: String = "",
)

@Serializable
data class UserDto(
    val id: Int,
    val email: String,
    val name: String = "",
    val phone: String = "",
    val role: String = "citizen",
)

@Serializable
data class NotificationDto(
    val id: Int,
    val title: String,
    val body: String = "",
    val report: String? = null,
    @SerialName("is_read") val isRead: Boolean = false,
    @SerialName("created_at") val createdAt: String = "",
)

@Serializable
data class DeviceRequest(
    @SerialName("fcm_token") val fcmToken: String,
    val platform: String = "android",
)

@Serializable
data class CommentRequest(val body: String)

@Serializable
data class StatusRequest(
    @SerialName("to_status") val toStatus: String,
    val note: String = "",
)

@Serializable
data class HealthDto(
    val status: String = "",
    val weights: String = "",
    // Typed rather than Map<String,String>: this field is a bool and would
    // blow up a string-valued map at deserialisation.
    @SerialName("weights_present") val weightsPresent: Boolean = false,
)

@Serializable
data class ApiErrorBody(val error: ApiErrorDetail)

@Serializable
data class ApiErrorDetail(
    val code: String = "error",
    val message: String = "Something went wrong",
    val fields: Map<String, List<String>> = emptyMap(),
)

// --- endpoints ------------------------------------------------------------

interface PotholeApi {

    @POST("auth/register/")
    suspend fun register(@Body body: RegisterRequest): UserDto

    @POST("auth/login/")
    suspend fun login(@Body body: LoginRequest): TokenPair

    @POST("auth/refresh/")
    suspend fun refresh(@Body body: RefreshRequest): TokenPair

    @GET("auth/me/")
    suspend fun me(): UserDto

    @Multipart
    @POST("reports/")
    suspend fun createReport(
        @Part image: MultipartBody.Part,
        @Part("latitude") latitude: RequestBody,
        @Part("longitude") longitude: RequestBody,
        @Part("accuracy_m") accuracyM: RequestBody?,
        @Part("captured_at") capturedAt: RequestBody?,
        @Part("notes") notes: RequestBody?,
        @Part("client_uuid") clientUuid: RequestBody,
        @Part("source") source: RequestBody,
    ): ReportEnvelope

    @GET("reports/")
    suspend fun reports(
        @Query("page") page: Int = 1,
        @Query("status") status: String? = null,
        @Query("severity") severity: String? = null,
    ): Page<ReportDto>

    @GET("reports/{id}/")
    suspend fun report(@Path("id") id: String): ReportDto

    @POST("reports/{id}/comments/")
    suspend fun addComment(@Path("id") id: String, @Body body: CommentRequest)

    @GET("reports/nearby/")
    suspend fun nearby(
        @Query("lat") lat: Double,
        @Query("lng") lng: Double,
        @Query("radius") radius: Double = 1000.0,
    ): List<ReportDto>

    @GET("notifications/")
    suspend fun notifications(@Query("page") page: Int = 1): Page<NotificationDto>

    @PATCH("notifications/{id}/read/")
    suspend fun markRead(@Path("id") id: Int)

    @POST("devices/")
    suspend fun registerDevice(@Body body: DeviceRequest)

    @DELETE("devices/")
    suspend fun unregisterDevice(@Body body: DeviceRequest)

    @GET("tasks/")
    suspend fun officerTasks(): List<ReportDto>

    @PATCH("reports/{id}/status/")
    suspend fun setStatus(@Path("id") id: String, @Body body: StatusRequest): ReportDto

    /** Liveness probe, used by the Profile screen's "Save & test". */
    @GET("health/")
    suspend fun health(): HealthDto
}
