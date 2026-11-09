package com.genaijerry.mirror.ui

import android.util.Log
import android.util.Size
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.genaijerry.mirror.CameraTextAnalyzer
import com.genaijerry.mirror.CropGeometry
import com.genaijerry.mirror.FrameTranslator
import com.genaijerry.mirror.LoggingFrameTranslator
import com.genaijerry.mirror.R
import com.genaijerry.mirror.RefreshLoop
import com.genaijerry.mirror.TextAnchor
import com.genaijerry.mirror.TextRegionTracker
import java.util.concurrent.Executors
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

private const val TAG = "CameraPreview"

/**
 * The short edge of the frames the detector is given; the long one is the same
 * as the picture the backend is sent.
 */
private const val ANALYSIS_SHORT_EDGE_PX = 720

/**
 * The live camera view, filling whatever space it is given, watching what it
 * sees for text.
 *
 * Two things run while this is on screen. The camera's frames go to the
 * on-device detector, which keeps [onAnchorChanged] told where the text sits,
 * so an overlay can follow it. And the refresh cycle runs by itself — every
 * [refreshIntervalMillis] at the earliest, one at a time — cutting the text
 * out of the newest frame and handing it to [translator].
 *
 * @param translator where each crop goes. The default only writes a log line;
 *   the translated overlay task passes the backend client in.
 */
@Composable
fun CameraPreview(
    modifier: Modifier = Modifier,
    translator: FrameTranslator = LoggingFrameTranslator,
    onAnchorChanged: (TextAnchor?) -> Unit = {},
    refreshIntervalMillis: Long = RefreshLoop.DEFAULT_INTERVAL_MILLIS,
) {
    val lifecycleOwner = LocalLifecycleOwner.current
    val description = stringResource(R.string.camera_preview_description)

    val reportAnchor = rememberUpdatedState(onAnchorChanged)
    val tracker = remember { TextRegionTracker(onAnchorChanged = { reportAnchor.value(it) }) }
    val analyzer = remember { CameraTextAnalyzer(tracker) }
    val analysisThread = remember { Executors.newSingleThreadExecutor() }

    DisposableEffect(analyzer, analysisThread) {
        onDispose {
            analyzer.close()
            analysisThread.shutdown()
            tracker.forget()
        }
    }

    LaunchedEffect(translator, refreshIntervalMillis) {
        // Off the main thread: a cycle cuts a picture up and encodes it, which
        // is too much work to do where the screen is drawn.
        withContext(Dispatchers.Default) {
            RefreshLoop(
                tracker = tracker,
                crops = analyzer,
                translator = translator,
                minimumIntervalMillis = refreshIntervalMillis,
                onCycleFailed = { failure -> Log.w(TAG, "A refresh cycle failed", failure) },
            ).run()
        }
    }

    AndroidView(
        modifier = modifier.semantics { contentDescription = description },
        factory = { viewContext ->
            val previewView = PreviewView(viewContext).apply {
                scaleType = PreviewView.ScaleType.FILL_CENTER
                implementationMode = PreviewView.ImplementationMode.COMPATIBLE
            }

            val providerFuture = ProcessCameraProvider.getInstance(viewContext)
            providerFuture.addListener({
                runCatching {
                    val provider = providerFuture.get()
                    val preview = Preview.Builder().build().also {
                        it.setSurfaceProvider(previewView.surfaceProvider)
                    }
                    // Only the newest frame is worth looking at: an older one
                    // is a picture of where the text used to be. The frames
                    // are asked to be as wide as the picture the backend is
                    // sent, because a crop of a headline out of a small frame
                    // is too coarse to read.
                    val analysis = ImageAnalysis.Builder()
                        .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                        .setResolutionSelector(
                            ResolutionSelector.Builder()
                                .setResolutionStrategy(
                                    ResolutionStrategy(
                                        Size(
                                            CropGeometry.MAX_LONG_EDGE_PX,
                                            ANALYSIS_SHORT_EDGE_PX,
                                        ),
                                        ResolutionStrategy
                                            .FALLBACK_RULE_CLOSEST_HIGHER_THEN_LOWER,
                                    ),
                                )
                                .build(),
                        )
                        .build()
                        .also { it.setAnalyzer(analysisThread, analyzer) }

                    provider.unbindAll()
                    provider.bindToLifecycle(
                        lifecycleOwner,
                        CameraSelector.DEFAULT_BACK_CAMERA,
                        preview,
                        analysis,
                    )
                }.onFailure { failure ->
                    // A phone with no usable back camera leaves the view blank
                    // rather than crashing the app.
                    Log.e(TAG, "The camera could not be started", failure)
                }
            }, ContextCompat.getMainExecutor(viewContext))

            previewView
        },
    )
}
