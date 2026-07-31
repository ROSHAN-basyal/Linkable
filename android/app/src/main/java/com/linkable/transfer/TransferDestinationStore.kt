package com.linkable.transfer

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

object TransferDestinationStore {
    private val _label = MutableStateFlow("/Linkable/{images,videos,pdfs,apks,files}")
    val label: StateFlow<String> = _label.asStateFlow()

    fun initialize() {
        _label.value = "/Linkable/{images,videos,pdfs,apks,files}"
    }
}
