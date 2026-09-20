package dev.potholewatch.app.di

import android.content.Context
import androidx.room.Room
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import dev.potholewatch.app.data.db.AppDatabase
import dev.potholewatch.app.data.db.PendingReportDao
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object AppModule {

    @Provides
    @Singleton
    fun database(@ApplicationContext context: Context): AppDatabase =
        Room.databaseBuilder(context, AppDatabase::class.java, "potholewatch.db")
            .fallbackToDestructiveMigration()
            .build()

    @Provides
    fun pendingReportDao(db: AppDatabase): PendingReportDao = db.pendingReports()
}
