package com.linkable.apps

import android.content.Context

class SharedAppsStore(context: Context) {
    private val preferences = context.getSharedPreferences("linkable_shared_apps", Context.MODE_PRIVATE)

    fun isShared(packageName: String): Boolean = preferences.getBoolean(packageName, false)

    fun setShared(packageName: String, shared: Boolean) {
        preferences.edit().putBoolean(packageName, shared).apply()
    }

    fun sharedPackages(): Set<String> {
        return preferences.all
            .filterValues { value -> value == true }
            .keys
    }
}
