package com.linkable.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val LightScheme = lightColorScheme(
    primary = Color(0xFF0F766E),
    onPrimary = Color(0xFFFFFAF0),
    primaryContainer = Color(0xFFC9EEE0),
    onPrimaryContainer = Color(0xFF10231F),
    secondary = Color(0xFF8A5A21),
    secondaryContainer = Color(0xFFF1E0C5),
    tertiary = Color(0xFFB45309),
    tertiaryContainer = Color(0xFFFFEDD5),
    background = Color(0xFFF5F2EA),
    surface = Color(0xFFFFFAF0),
    surfaceVariant = Color(0xFFE8E2D4),
)

private val DarkScheme = darkColorScheme(
    primary = Color(0xFF5EEAD4),
    primaryContainer = Color(0xFF134E4A),
    secondaryContainer = Color(0xFF4B341C),
    tertiaryContainer = Color(0xFF5C2D0C),
    background = Color(0xFF101820),
    surface = Color(0xFF14232B),
    surfaceVariant = Color(0xFF20313A),
)

@Composable
fun LinkableTheme(
    darkTheme: Boolean = false,
    content: @Composable () -> Unit,
) {
    MaterialTheme(
        colorScheme = if (darkTheme) DarkScheme else LightScheme,
        content = content,
    )
}
