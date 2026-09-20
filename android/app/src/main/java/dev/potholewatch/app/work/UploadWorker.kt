package dev.potholewatch.app.work

import android.content.Context
import androidx.hilt.work.HiltWorker
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import dev.potholewatch.app.data.db.PendingReportDao
import dev.potholewatch.app.data.repo.Uploader
import retrofit2.HttpException

/**
 * Drains the offline queue.
 *
 * A 4xx (other than 401/408/429) means the server will never accept this row,
 * so it is dropped rather than retried forever. Anything else is transient and
 * WorkManager backs off.
 */
@HiltWorker
class UploadWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted params: WorkerParameters,
    private val dao: PendingReportDao,
    private val uploader: Uploader,
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val rows = dao.all()
        if (rows.isEmpty()) return Result.success()

        var transientFailure = false
        for (row in rows) {
            try {
                uploader.upload(row)
                dao.delete(row.clientUuid)
            } catch (e: HttpException) {
                val code = e.code()
                val permanent = code in 400..499 && code !in setOf(401, 408, 429)
                dao.recordFailure(row.clientUuid, "HTTP $code")
                if (permanent) {
                    dao.delete(row.clientUuid)
                } else {
                    transientFailure = true
                }
            } catch (e: IllegalArgumentException) {
                // The captured file is gone; the row can never succeed.
                dao.delete(row.clientUuid)
            } catch (e: Exception) {
                dao.recordFailure(row.clientUuid, e.message)
                transientFailure = true
            }
        }
        return if (transientFailure) Result.retry() else Result.success()
    }
}
