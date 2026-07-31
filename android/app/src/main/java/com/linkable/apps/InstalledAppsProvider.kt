package com.linkable.apps

import android.content.Context
import android.content.Intent
import android.content.pm.ApplicationInfo
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.drawable.Drawable
import com.google.protobuf.ByteString
import com.linkable.notifications.NotificationBlocklistStore
import com.linkable.protocol.v1.SharedAppShortcut
import java.io.ByteArrayOutputStream

data class InstalledApp(
    val packageName: String,
    val label: String,
    val category: String,
    val shared: Boolean,
    val notificationBlocked: Boolean,
)

class InstalledAppsProvider(private val context: Context) {
    private val packageManager = context.packageManager
    private val sharedAppsStore = SharedAppsStore(context)
    private val notificationBlocklistStore = NotificationBlocklistStore(context)

    fun installedApps(deviceId: String = ""): List<InstalledApp> {
        val intent = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
        return packageManager.queryIntentActivities(intent, 0)
            .map { resolveInfo ->
                val packageName = resolveInfo.activityInfo.packageName
                InstalledApp(
                    packageName = packageName,
                    label = resolveInfo.loadLabel(packageManager).toString(),
                    category = categoryFor(resolveInfo.activityInfo.applicationInfo),
                    shared = sharedAppsStore.isShared(packageName),
                    notificationBlocked = notificationBlocklistStore.isBlocked(deviceId, packageName),
                )
            }
            .distinctBy { it.packageName }
            .sortedBy { it.label.lowercase() }
    }

    fun sharedShortcuts(): List<SharedAppShortcut> {
        val sharedPackages = sharedAppsStore.sharedPackages()
        if (sharedPackages.isEmpty()) return emptyList()
        val intent = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
        return packageManager.queryIntentActivities(intent, 0)
            .filter { it.activityInfo.packageName in sharedPackages }
            .distinctBy { it.activityInfo.packageName }
            .sortedBy { it.loadLabel(packageManager).toString().lowercase() }
            .map { resolveInfo ->
                SharedAppShortcut.newBuilder()
                    .setPackageName(resolveInfo.activityInfo.packageName)
                    .setLabel(resolveInfo.loadLabel(packageManager).toString())
                    .setCategory(categoryFor(resolveInfo.activityInfo.applicationInfo))
                    .setIconPng(ByteString.copyFrom(iconPng(resolveInfo.loadIcon(packageManager))))
                    .setIconMime("image/png")
                    .build()
            }
    }

    fun setShared(packageName: String, shared: Boolean) {
        sharedAppsStore.setShared(packageName, shared)
    }

    fun setNotificationBlocked(deviceId: String, packageName: String, blocked: Boolean) {
        notificationBlocklistStore.setBlocked(deviceId, packageName, blocked)
    }

    private fun categoryFor(info: ApplicationInfo): String {
        return when (info.category) {
            ApplicationInfo.CATEGORY_GAME -> "Games"
            ApplicationInfo.CATEGORY_AUDIO -> "Audio"
            ApplicationInfo.CATEGORY_VIDEO -> "Video"
            ApplicationInfo.CATEGORY_IMAGE -> "Images"
            ApplicationInfo.CATEGORY_SOCIAL -> "Social"
            ApplicationInfo.CATEGORY_NEWS -> "News"
            ApplicationInfo.CATEGORY_MAPS -> "Maps"
            ApplicationInfo.CATEGORY_PRODUCTIVITY -> "Productivity"
            else -> "Other"
        }
    }

    private fun iconPng(drawable: Drawable): ByteArray {
        val bitmap = Bitmap.createBitmap(96, 96, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bitmap)
        drawable.setBounds(0, 0, canvas.width, canvas.height)
        drawable.draw(canvas)
        return ByteArrayOutputStream().use { output ->
            bitmap.compress(Bitmap.CompressFormat.PNG, 90, output)
            output.toByteArray()
        }
    }
}
