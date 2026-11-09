package com.genaijerry.mirror

import android.graphics.Rect
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Where the detector says the text is, turned into fractions of the view.
 *
 * The analyzer itself needs a camera frame and ML Kit's native library, so a
 * person on a phone proves it (the system test plan's ST-1 and ST-2). This
 * covers the one piece of it that is arithmetic: the step that decides where
 * on screen the app believes the text sits, and therefore which part of the
 * picture a refresh cycle cuts out.
 */
@RunWith(AndroidJUnit4::class)
class CameraTextAnalyzerTest {

    @Test
    fun a_detected_box_becomes_its_share_of_the_frame() {
        val box = Rect(/* left = */ 160, /* top = */ 120, /* right = */ 480, /* bottom = */ 240)

        val region = box.asNormalized(width = 640, height = 480)

        assertRect(NormalizedRect(x = 0.25f, y = 0.25f, width = 0.5f, height = 0.25f), region)
    }

    @Test
    fun a_box_the_detector_ran_past_the_frame_is_cut_back_to_the_view() {
        val box = Rect(/* left = */ -40, /* top = */ 0, /* right = */ 700, /* bottom = */ 480)

        val region = box.asNormalized(width = 640, height = 480)

        assertRect(NormalizedRect(x = 0f, y = 0f, width = 1f, height = 1f), region)
    }
}
