package com.linkable.debug

import android.util.Log
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update

data class DebugEvent(
    val timestampMs: Long,
    val category: String,
    val message: String,
)

object DebugEventLog {
    private val _events = MutableStateFlow<List<DebugEvent>>(emptyList())
    val events: StateFlow<List<DebugEvent>> = _events.asStateFlow()

    fun record(category: String, message: String) {
        Log.i("Linkable", "[$category] $message")
        val event = DebugEvent(
            timestampMs = System.currentTimeMillis(),
            category = category,
            message = message,
        )
        _events.update { current -> (current + event).takeLast(80) }
    }
}
