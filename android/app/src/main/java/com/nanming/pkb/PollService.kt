package com.nanming.pkb

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

class PollService : Service() {

    companion object {
        const val CHANNEL_CALL = "pkb_call"
        const val CHANNEL_RUNNING = "pkb_running"
        const val NOTIF_CALL_ID = 10
        const val NOTIF_RUNNING_ID = 1
        const val INTERVAL_MS = 3000L

        fun start(context: Context) {
            val intent = Intent(context, PollService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, PollService::class.java))
        }
    }

    private val handler = Handler(Looper.getMainLooper())
    private val executor = Executors.newSingleThreadExecutor()
    private lateinit var prefs: Prefs
    private var lastActivate = 0

    private val tick = object : Runnable {
        override fun run() {
            pollOnce()
            handler.postDelayed(this, INTERVAL_MS)
        }
    }

    override fun onCreate() {
        super.onCreate()
        prefs = Prefs(this)
        lastActivate = prefs.lastActivate
        createChannels()
        startForeground(NOTIF_RUNNING_ID, buildRunningNotification())
        handler.post(tick)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        return START_STICKY
    }

    override fun onDestroy() {
        handler.removeCallbacks(tick)
        executor.shutdownNow()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun createChannels() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = getSystemService(NotificationManager::class.java)
        val call = NotificationChannel(
            CHANNEL_CALL,
            getString(R.string.notif_channel_name),
            NotificationManager.IMPORTANCE_HIGH
        ).apply {
            description = getString(R.string.notif_channel_desc)
            enableVibration(true)
            vibrationPattern = longArrayOf(0, 180, 90, 180)
            enableLights(true)
        }
        val running = NotificationChannel(
            CHANNEL_RUNNING,
            "后台待命",
            NotificationManager.IMPORTANCE_LOW
        ).apply {
            description = "保持与电脑的连接，关闭后收不到呼叫提醒"
            setShowBadge(false)
        }
        manager.createNotificationChannel(call)
        manager.createNotificationChannel(running)
    }

    private fun buildRunningNotification(): Notification {
        val open = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, CHANNEL_RUNNING)
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(this)
        }
        return builder
            .setContentTitle(getString(R.string.notif_running))
            .setContentText("电脑呼叫时会在通知栏提醒")
            .setSmallIcon(R.drawable.ic_notification)
            .setContentIntent(open)
            .setOngoing(true)
            .build()
    }

    private fun pollOnce() {
        val base = prefs.baseUrl
        val token = prefs.token
        if (base.isEmpty() || token.isEmpty()) return
        executor.execute {
            try {
                val conn = URL("$base/heartbeat").openConnection() as HttpURLConnection
                conn.requestMethod = "POST"
                conn.connectTimeout = 4000
                conn.readTimeout = 4000
                conn.doOutput = true
                conn.setRequestProperty("X-Token", token)
                conn.setRequestProperty("X-Device-Id", prefs.deviceId)
                conn.setRequestProperty("Content-Length", "0")
                val code = conn.responseCode
                if (code in 200..299) {
                    val body = conn.inputStream.bufferedReader().use { it.readText() }
                    val json = JSONObject(body)
                    val activate = json.optInt("activate", 0)
                    if (activate > lastActivate) {
                        lastActivate = activate
                        prefs.lastActivate = activate
                        showCallNotification()
                    }
                }
                conn.disconnect()
            } catch (_: Exception) {
            }
        }
    }

    private fun showCallNotification() {
        val manager = getSystemService(NotificationManager::class.java)
        val open = PendingIntent.getActivity(
            this,
            1,
            Intent(this, MainActivity::class.java).apply {
                addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP)
                putExtra("from_call", true)
            },
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, CHANNEL_CALL)
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(this)
        }
        val notification = builder
            .setContentTitle(getString(R.string.notif_call_title))
            .setContentText(getString(R.string.notif_call_body))
            .setSmallIcon(R.drawable.ic_notification)
            .setContentIntent(open)
            .setAutoCancel(true)
            .setPriority(Notification.PRIORITY_HIGH)
            .setDefaults(Notification.DEFAULT_SOUND or Notification.DEFAULT_VIBRATE)
            .build()
        manager.notify(NOTIF_CALL_ID, notification)
    }
}
