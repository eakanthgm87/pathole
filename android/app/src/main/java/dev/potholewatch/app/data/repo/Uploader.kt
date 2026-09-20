package dev.potholewatch.app.data.repo

import dev.potholewatch.app.data.api.PotholeApi
import dev.potholewatch.app.data.api.ReportDto
import dev.potholewatch.app.data.db.PendingReport
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import javax.inject.Inject
import javax.inject.Singleton
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody

/** Turns a queued row into a multipart POST. Shared by the foreground path
 *  and the WorkManager retry path so both send identical requests. */
@Singleton
class Uploader @Inject constructor(private val api: PotholeApi) {

    private val iso = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US).apply {
        timeZone = TimeZone.getTimeZone("UTC")
    }

    suspend fun upload(row: PendingReport): ReportDto {
        val file = File(row.imagePath)
        require(file.exists()) { "Captured image is missing: ${row.imagePath}" }

        val part = MultipartBody.Part.createFormData(
            "image", file.name, file.asRequestBody("image/jpeg".toMediaType())
        )
        fun text(value: String?) = value?.toRequestBody("text/plain".toMediaType())

        val envelope = api.createReport(
            image = part,
            latitude = text(row.latitude.toString())!!,
            longitude = text(row.longitude.toString())!!,
            accuracyM = text(row.accuracyM?.toString()),
            capturedAt = text(iso.format(Date(row.capturedAt))),
            notes = text(row.notes),
            clientUuid = text(row.clientUuid)!!,
            source = text("android")!!,
        )
        // The upload succeeded, so the local copy is no longer the only one.
        runCatching { file.delete() }
        return envelope.report
    }
}
