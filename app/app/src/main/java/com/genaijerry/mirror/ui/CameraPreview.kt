package com.genaijerry.mirror.ui

import android.util.Log
import androidx.camera.core.CameraSelector
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.genaijerry.mirror.R

private const val TAG = "CameraPreview"

/**
 * The live camera view, filling whatever space it is given.
 *
 * CameraX is bound to the current lifecycle, so the camera starts and stops
 * with the screen. Later tasks add the frame analysis that finds text; this
 * task shows the view and nothing more.
 */
@Composable
fun CameraPreview(modifier: Modifier = Modifier) {
    val lifecycleOwner = LocalLifecycleOwner.current
    val description = stringResource(R.string.camera_preview_description)

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
                    provider.unbindAll()
                    provider.bindToLifecycle(
                        lifecycleOwner,
                        CameraSelector.DEFAULT_BACK_CAMERA,
                        preview,
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
