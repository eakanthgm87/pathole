package dev.potholewatch.app.data.db

import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.RoomDatabase
import kotlinx.coroutines.flow.Flow

/**
 * A report captured on the device and not yet accepted by the server.
 *
 * [clientUuid] is generated at capture time and sent with every retry, so the
 * server can make the upload idempotent. Without it, a flaky network produces
 * duplicate reports of the same pothole.
 */
@Entity(tableName = "pending_reports")
data class PendingReport(
    @PrimaryKey val clientUuid: String,
    val imagePath: String,
    val latitude: Double,
    val longitude: Double,
    val accuracyM: Double?,
    val notes: String = "",
    val capturedAt: Long = System.currentTimeMillis(),
    val attempts: Int = 0,
    val lastError: String? = null,
)

@Dao
interface PendingReportDao {

    @Insert
    suspend fun insert(report: PendingReport)

    @Query("SELECT * FROM pending_reports ORDER BY capturedAt ASC")
    fun observeAll(): Flow<List<PendingReport>>

    @Query("SELECT * FROM pending_reports ORDER BY capturedAt ASC")
    suspend fun all(): List<PendingReport>

    @Query("SELECT COUNT(*) FROM pending_reports")
    fun count(): Flow<Int>

    @Query("DELETE FROM pending_reports WHERE clientUuid = :uuid")
    suspend fun delete(uuid: String)

    @Query("UPDATE pending_reports SET attempts = attempts + 1, lastError = :error WHERE clientUuid = :uuid")
    suspend fun recordFailure(uuid: String, error: String?)
}

@Database(entities = [PendingReport::class], version = 1, exportSchema = false)
abstract class AppDatabase : RoomDatabase() {
    abstract fun pendingReports(): PendingReportDao
}
