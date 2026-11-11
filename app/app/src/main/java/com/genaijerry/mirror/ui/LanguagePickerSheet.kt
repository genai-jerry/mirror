package com.genaijerry.mirror.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.genaijerry.mirror.LanguageOption
import com.genaijerry.mirror.LanguagePair
import com.genaijerry.mirror.LanguagePickerState
import com.genaijerry.mirror.LanguagesStatus
import com.genaijerry.mirror.R

/** Test tags the unit tests address the picker by. */
object LanguagePickerTags {
    const val OPEN = "picker.open"
    const val SHEET = "picker.sheet"
    const val LOADING = "picker.loading"
    const val UNAVAILABLE = "picker.unavailable"
    const val CLOSE = "picker.close"

    fun source(code: String) = "picker.source.$code"

    fun target(code: String) = "picker.target.$code"
}

/**
 * The button that opens the picker, showing the pair in force.
 *
 * It sits above the camera view, so the languages can be changed at any time
 * without leaving the one screen this app has.
 */
@Composable
fun LanguageBar(
    state: LanguagePickerState,
    onOpenPicker: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier,
        color = MaterialTheme.colorScheme.surface.copy(alpha = 0.85f),
        shape = MaterialTheme.shapes.small,
    ) {
        TextButton(
            onClick = onOpenPicker,
            modifier = Modifier.testTag(LanguagePickerTags.OPEN),
        ) {
            Text(
                text = stringResource(
                    R.string.languages_pair,
                    state.catalogue.nameOf(state.pair.source),
                    state.catalogue.nameOf(state.pair.target),
                ),
                style = MaterialTheme.typography.labelLarge,
            )
        }
    }
}

/**
 * The picker itself: a sheet over the camera listing what the backend offers.
 *
 * The lists are whatever `GET /v1/languages` last answered — this screen
 * holds no list of its own, which is the whole point of serving them from
 * backend configuration.
 */
@Composable
fun LanguagePickerSheet(
    state: LanguagePickerState,
    onChoose: (LanguagePair) -> Unit,
    onClose: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Box(
        modifier = modifier.fillMaxSize(),
        contentAlignment = Alignment.BottomCenter,
    ) {
        Surface(
            modifier = Modifier.fillMaxWidth().testTag(LanguagePickerTags.SHEET),
            color = MaterialTheme.colorScheme.surface,
            shape = MaterialTheme.shapes.large,
            tonalElevation = 6.dp,
        ) {
            Column(modifier = Modifier.padding(24.dp)) {
                Text(
                    text = stringResource(R.string.languages_title),
                    style = MaterialTheme.typography.titleLarge,
                )
                if (state.catalogue.isEmpty) {
                    EmptyNotice(state.status)
                } else {
                    Column(
                        modifier = Modifier.heightIn(max = 420.dp).verticalScroll(
                            rememberScrollState(),
                        ),
                    ) {
                        SectionHeading(stringResource(R.string.languages_from))
                        state.catalogue.sources.forEach { option ->
                            LanguageRow(
                                option = option,
                                chosen = option.code == state.pair.source,
                                tag = LanguagePickerTags.source(option.code),
                                onClick = { onChoose(state.pair.copy(source = option.code)) },
                            )
                        }
                        SectionHeading(stringResource(R.string.languages_to))
                        state.catalogue.targets.forEach { option ->
                            LanguageRow(
                                option = option,
                                chosen = option.code == state.pair.target,
                                tag = LanguagePickerTags.target(option.code),
                                onClick = { onChoose(state.pair.copy(target = option.code)) },
                            )
                        }
                    }
                }
                TextButton(
                    onClick = onClose,
                    modifier = Modifier
                        .align(Alignment.End)
                        .testTag(LanguagePickerTags.CLOSE),
                ) {
                    Text(stringResource(R.string.languages_close))
                }
            }
        }
    }
}

@Composable
private fun EmptyNotice(status: LanguagesStatus) {
    val (tag, text) = when (status) {
        LanguagesStatus.Unavailable ->
            LanguagePickerTags.UNAVAILABLE to stringResource(R.string.languages_unavailable)

        else -> LanguagePickerTags.LOADING to stringResource(R.string.languages_loading)
    }
    Text(
        text = text,
        style = MaterialTheme.typography.bodyMedium,
        modifier = Modifier.padding(vertical = 16.dp).testTag(tag),
    )
}

@Composable
private fun SectionHeading(text: String) {
    Text(
        text = text,
        style = MaterialTheme.typography.labelMedium,
        modifier = Modifier.padding(top = 16.dp, bottom = 4.dp),
    )
}

@Composable
private fun LanguageRow(
    option: LanguageOption,
    chosen: Boolean,
    tag: String,
    onClick: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .testTag(tag)
            .padding(vertical = 12.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(
            text = option.name,
            style = MaterialTheme.typography.bodyLarge,
            fontWeight = if (chosen) FontWeight.Bold else FontWeight.Normal,
        )
        if (chosen) {
            Text(
                text = stringResource(R.string.languages_chosen),
                style = MaterialTheme.typography.labelMedium,
            )
        }
    }
}
