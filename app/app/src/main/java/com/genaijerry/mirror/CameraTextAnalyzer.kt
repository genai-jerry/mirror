package com.genaijerry.mirror

import android.graphics.Bitmap
import android.graphics.Matrix
import android.util.Log
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.core.graphics.scale
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.TextRecognizer
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import java.io.ByteArrayOutputStream

private const val TAG = "CameraTextAnalyzer"

/**
 * Watches the camera's frames for text and keeps the newest frame to hand.
 *
 * It does the two device-side jobs of this task at once, because both need
 * every frame:
 *
 *  - it asks the on-device recognizer **where** text is and tells the
 *    [tracker], frame by frame, so the anchor follows the text;
 *  - it keeps the newest frame, so a refresh cycle can cut the anchor's
 *    rectangle out of a real picture.
 *
 * What the recognizer *reads* is thrown away. Only its rectangles are used:
 * the reading is Sarvam's job, through the backend (design decision D4).
 */
class CameraTextAnalyzer(
    private val tracker: TextRegionTracker,
    openRecognizer: () -> TextRecognizer = {
        TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
    },
) : ImageAnalysis.Analyzer, FrameCropSource, AutoCloseable {

    /**
     * Opened on the first frame, not in the constructor: a screen that never
     * gets a frame — a phone with no usable camera, a unit test — never loads
     * the recognizer at all.
     */
    private val lazyRecognizer: Lazy<TextRecognizer> = lazy(openRecognizer)

    /**
     * The newest frame, turned the way a person holds the phone. Written by
     * the camera's analysis thread, read by the refresh cycle, so it is
     * volatile. A replaced frame is left to the garbage collector rather than
     * recycled, because a cycle may be reading it at that moment.
     */
    @Volatile
    private var newestFrame: Bitmap? = null

    override fun analyze(image: ImageProxy) {
        val upright = try {
            image.toBitmap().uprightBy(image.imageInfo.rotationDegrees)
        } catch (failure: Throwable) {
            Log.w(TAG, "A camera frame could not be read", failure)
            image.close()
            return
        }
        newestFrame = upright

        try {
            lazyRecognizer.value.process(InputImage.fromBitmap(upright, 0))
                .addOnSuccessListener { text ->
                    tracker.onTextLocated(
                        text.textBlocks.mapNotNull { block ->
                            block.boundingBox?.asNormalized(upright.width, upright.height)
                        },
                    )
                }
                .addOnFailureListener { failure ->
                    // A frame the recognizer cannot handle counts as a frame
                    // with no text in it, which is what engages the
                    // middle-of-the-view fallback.
                    Log.w(TAG, "The text recognizer refused a frame", failure)
                    tracker.onTextLocated(emptyList())
                }
                .addOnCompleteListener { image.close() }
        } catch (failure: Throwable) {
            Log.w(TAG, "The text recognizer could not be started", failure)
            image.close()
        }
    }

    override fun crop(region: NormalizedRect): FrameCrop? {
        val frame = newestFrame ?: return null
        val inView = region.clampedToView()
        val cut = CropGeometry.pixelRect(inView, frame.width, frame.height)
        val cutOut = Bitmap.createBitmap(frame, cut.left, cut.top, cut.width, cut.height)
        val size = CropGeometry.downscaled(cutOut.width, cutOut.height)
        val sent =
            if (size.width == cutOut.width && size.height == cutOut.height) {
                cutOut
            } else {
                cutOut.scale(size.width, size.height)
            }

        val jpeg = ByteArrayOutputStream().use { bytes ->
            sent.compress(Bitmap.CompressFormat.JPEG, CropGeometry.JPEG_QUALITY, bytes)
            bytes.toByteArray()
        }

        if (sent !== cutOut) sent.recycle()
        if (cutOut !== frame) cutOut.recycle()

        return FrameCrop(jpeg = jpeg, region = inView)
    }

    override fun close() {
        newestFrame = null
        if (!lazyRecognizer.isInitialized()) return
        runCatching { lazyRecognizer.value.close() }
            .onFailure { Log.w(TAG, "The text recognizer did not close cleanly", it) }
    }
}

/** This frame turned [rotationDegrees] clockwise, so its text reads level. */
private fun Bitmap.uprightBy(rotationDegrees: Int): Bitmap {
    if (rotationDegrees % 360 == 0) return this
    val turn = Matrix().apply { postRotate(rotationDegrees.toFloat()) }
    val upright = Bitmap.createBitmap(this, 0, 0, width, height, turn, true)
    if (upright !== this) recycle()
    return upright
}

/**
 * This pixel rectangle as fractions of a frame [width] × [height] pixels.
 *
 * Internal rather than private so the unit suite can pin it: this is the step
 * that decides where on screen the app believes the text sits.
 */
internal fun android.graphics.Rect.asNormalized(width: Int, height: Int): NormalizedRect =
    NormalizedRect(
        x = left.toFloat() / width,
        y = top.toFloat() / height,
        width = this.width().toFloat() / width,
        height = this.height().toFloat() / height,
    ).clampedToView()
