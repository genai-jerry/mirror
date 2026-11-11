package com.genaijerry.mirror

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.genaijerry.mirror.ui.CameraPermissionStatus
import com.genaijerry.mirror.ui.CameraPreview
import com.genaijerry.mirror.ui.MainScreen
import com.genaijerry.mirror.ui.MirrorTheme
import kotlinx.coroutines.launch

/**
 * The app is one screen: the live camera view with the translated text drawn
 * over it, the camera permission asked for once on the way in, and the
 * language picker reachable above both.
 */
class MainActivity : ComponentActivity() {

    private var permissionStatus by mutableStateOf(CameraPermissionStatus.NotAsked)

    /**
     * The translation showing on the camera. It belongs to the screen rather
     * than to the app: there is nothing worth keeping about where text sat in
     * a camera view that has closed.
     */
    private val overlay = TranslatedOverlayState()

    private val mirror: MirrorApplication
        get() = application as MirrorApplication

    private val languages: LanguageSelection
        get() = mirror.languages

    private val requestCameraPermission =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
            permissionStatus =
                if (granted) CameraPermissionStatus.Granted else CameraPermissionStatus.Denied
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // The remembered pair and the backend's list of languages, read on the
        // way in. The picker reads the list again every time it opens.
        lifecycleScope.launch { languages.start() }
        setContent {
            MirrorTheme {
                MainScreen(
                    status = permissionStatus,
                    onRequestPermission = {
                        requestCameraPermission.launch(Manifest.permission.CAMERA)
                    },
                    onOpenSettings = ::openAppSettings,
                    languages = languages.state,
                    onOpenPicker = {
                        languages.open()
                        lifecycleScope.launch { languages.refresh() }
                    },
                    onClosePicker = languages::close,
                    onChooseLanguages = { pair ->
                        lifecycleScope.launch { languages.choose(pair) }
                    },
                    overlay = overlay.overlay,
                    cameraContent = {
                        CameraPreview(
                            translator = mirror.frames,
                            modifier = Modifier.fillMaxSize(),
                            onAnchorChanged = overlay::reanchor,
                            onTranslated = overlay::show,
                        )
                    },
                )
            }
        }
    }

    override fun onStart() {
        super.onStart()
        // Someone may have turned the camera on in Settings while we were away.
        if (hasCameraPermission()) {
            permissionStatus = CameraPermissionStatus.Granted
        }
    }

    private fun hasCameraPermission(): Boolean =
        ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) ==
            PackageManager.PERMISSION_GRANTED

    private fun openAppSettings() {
        startActivity(
            Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                data = Uri.fromParts("package", packageName, null)
            },
        )
    }
}
