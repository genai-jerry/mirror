package com.genaijerry.mirror.ui

/** Whether this app may use the camera, as the main screen sees it. */
enum class CameraPermissionStatus {
    /** Not asked yet in this session. The screen asks once. */
    NotAsked,

    /** Granted: the live camera view is shown. */
    Granted,

    /** Refused: the screen explains why the camera is needed and points at settings. */
    Denied,
}
