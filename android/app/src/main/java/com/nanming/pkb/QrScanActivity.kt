package com.nanming.pkb

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.util.Size
import android.widget.Button
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.google.zxing.BarcodeFormat
import com.google.zxing.BinaryBitmap
import com.google.zxing.DecodeHintType
import com.google.zxing.MultiFormatReader
import com.google.zxing.PlanarYUVLuminanceSource
import com.google.zxing.common.HybridBinarizer
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

/** 扫电脑端 PKB 窗口里显示的二维码，扫到后把整条地址回给 MainActivity。 */
class QrScanActivity : AppCompatActivity() {

    companion object {
        const val EXTRA_TEXT = "qr_text"
        private const val REQ_CAMERA = 3001
    }

    private lateinit var previewView: PreviewView
    private lateinit var executor: ExecutorService
    private val reader = MultiFormatReader().apply {
        setHints(
            mapOf(
                DecodeHintType.POSSIBLE_FORMATS to listOf(BarcodeFormat.QR_CODE),
                DecodeHintType.TRY_HARDER to true
            )
        )
    }

    @Volatile
    private var handled = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_qr_scan)
        previewView = findViewById(R.id.previewView)
        findViewById<Button>(R.id.closeBtn).setOnClickListener { finish() }
        executor = Executors.newSingleThreadExecutor()
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
            == PackageManager.PERMISSION_GRANTED
        ) {
            startCamera()
        } else {
            ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.CAMERA), REQ_CAMERA)
        }
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != REQ_CAMERA) return
        if (grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
            startCamera()
        } else {
            setResult(RESULT_CANCELED)
            finish()
        }
    }

    private fun startCamera() {
        val future = ProcessCameraProvider.getInstance(this)
        future.addListener({
            try {
                val provider = future.get()
                val preview = Preview.Builder().build().also {
                    it.setSurfaceProvider(previewView.surfaceProvider)
                }
                @Suppress("DEPRECATION")
                val analysis = ImageAnalysis.Builder()
                    .setTargetResolution(Size(1280, 720))
                    .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                    .build()
                analysis.setAnalyzer(executor) { image -> decode(image) }
                provider.unbindAll()
                provider.bindToLifecycle(
                    this, CameraSelector.DEFAULT_BACK_CAMERA, preview, analysis
                )
            } catch (_: Throwable) {
            }
        }, ContextCompat.getMainExecutor(this))
    }

    private fun decode(image: ImageProxy) {
        try {
            if (!handled) {
                val text = readQr(image)
                if (!text.isNullOrBlank()) {
                    handled = true
                    runOnUiThread {
                        setResult(RESULT_OK, Intent().putExtra(EXTRA_TEXT, text))
                        finish()
                    }
                }
            }
        } catch (_: Throwable) {
        } finally {
            image.close()
        }
    }

    private fun readQr(image: ImageProxy): String? {
        val width = image.width
        val height = image.height
        if (width <= 0 || height <= 0) return null
        val plane = image.planes[0]
        val buffer = plane.buffer.duplicate()
        buffer.rewind()
        val rowStride = plane.rowStride
        val pixelStride = plane.pixelStride
        val data: ByteArray
        val dataWidth: Int
        if (pixelStride == 1) {
            dataWidth = rowStride
            data = ByteArray(rowStride * height)
            val n = minOf(data.size, buffer.remaining())
            buffer.get(data, 0, n)
        } else {
            dataWidth = width
            data = ByteArray(width * height)
            val row = ByteArray(rowStride)
            for (y in 0 until height) {
                val n = minOf(rowStride, buffer.remaining())
                if (n <= 0) break
                buffer.get(row, 0, n)
                for (x in 0 until width) {
                    data[y * width + x] = row[x * pixelStride]
                }
            }
        }
        val source = PlanarYUVLuminanceSource(data, dataWidth, height, 0, 0, dataWidth, height, false)
        val bitmap = BinaryBitmap(HybridBinarizer(source))
        return try {
            reader.decodeWithState(bitmap).text
        } catch (_: Throwable) {
            null
        } finally {
            reader.reset()
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        executor.shutdown()
    }
}
