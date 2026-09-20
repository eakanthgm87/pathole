package dev.potholewatch.app.data.repo

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import dagger.hilt.android.qualifiers.ApplicationContext
import dev.potholewatch.app.data.api.PotholeApi
import dev.potholewatch.app.data.api.ReportDto
import dev.potholewatch.app.data.db.PendingReport
import dev.potholewatch.app.data.db.PendingReportDao
import dev.potholewatch.app.work.UploadWorker
import java.io.File
import java.util.UUID
import java.util.concurrent.TimeUnit
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.Flow

sealed interface SubmitResult {
    data class Uploaded(val report: ReportDto) : SubmitResult
    data class Queued(val clientUuid: String) : SubmitResult
}

@Singleton
class ReportRepository @Inject constructor(
    @ApplicationContext private val context: Context,
    private val api: PotholeApi,
    private val dao: PendingReportDao,
    private val uploader: Uploader,
) {

    val pending: Flow<List<PendingReport>> = dao.observeAll()
    val pendingCount: Flow<Int> = dao.count()

    /**
     * Always writes to the queue first, then tries to upload.
     *
     * Queue-then-send rather than send-then-queue: if the process dies mid
     * upload, the capture survives. A duplicate upload is harmless because the
     * server keys on clientUuid.
     */
    suspend fun submit(
        imageFile: File,
        latitude: Double,
        longitude: Double,
        accuracyM: Double?,
        notes: String,
    ): SubmitResult {
        val clientUuid = UUID.randomUUID().toString()
        val row = PendingReport(
            clientUuid = clientUuid,
            imagePath = imageFile.absolutePath,
            latitude = latitude,
            longitude = longitude,
            accuracyM = accuracyM,
            notes = notes,
        )
        dao.insert(row)

        return try {
            val report = uploader.upload(row)
            dao.delete(clientUuid)
            SubmitResult.Uploaded(report)
        } catch (e: Exception) {
            dao.recordFailure(clientUuid, e.message)
            scheduleFlush()
            SubmitResult.Queued(clientUuid)
        }
    }

    fun scheduleFlush(wifiOnly: Boolean = false) {
        val request = OneTimeWorkRequestBuilder<UploadWorker>()
            .setConstraints(
                Constraints.Builder()
                    .setRequiredNetworkType(
                        if (wifiOnly) NetworkType.UNMETERED else NetworkType.CONNECTED
                    )
                    .build()
            )
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
            .build()
        WorkManager.getInstance(context)
            .enqueueUniqueWork("pothole-upload", ExistingWorkPolicy.KEEP, request)
    }

    suspend fun discard(clientUuid: String) = dao.delete(clientUuid)

    suspend fun myReports(page: Int = 1) = api.reports(page = page)

    suspend fun report(id: String) = api.report(id)

    suspend fun nearby(lat: Double, lng: Double, radius: Double = 1500.0) =
        api.nearby(lat, lng, radius)

    suspend fun comment(id: String, body: String) =
        api.addComment(id, dev.potholewatch.app.data.api.CommentRequest(body))
}
