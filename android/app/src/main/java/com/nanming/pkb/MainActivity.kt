package com.nanming.pkb

import android.Manifest
import android.annotation.SuppressLint
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.view.View
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.EditText
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import java.net.Inet4Address
import java.net.InetSocketAddress
import java.net.NetworkInterface
import java.net.Socket
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicInteger

class MainActivity : AppCompatActivity() {

    private lateinit var prefs: Prefs
    private lateinit var webView: WebView
    private lateinit var setupScroll: ScrollView
    private lateinit var addressInput: EditText
    private lateinit var connectBtn: Button
    private lateinit var scanBtn: Button
    private lateinit var changeBtn: Button
    private lateinit var statusText: TextView
    private lateinit var foundList: TextView

    private val scanPool = Executors.newFixedThreadPool(40)

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        prefs = Prefs(this)

        webView = findViewById(R.id.webView)
        setupScroll = findViewById(R.id.setupScroll)
        addressInput = findViewById(R.id.addressInput)
        connectBtn = findViewById(R.id.connectBtn)
        scanBtn = findViewById(R.id.scanBtn)
        changeBtn = findViewById(R.id.changeBtn)
        statusText = findViewById(R.id.setupStatus)
        foundList = findViewById(R.id.foundList)

        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            useWideViewPort = true
            loadWithOverviewMode = true
            mediaPlaybackRequiresUserGesture = false
        }
        webView.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)
                syncDeviceId(view)
            }
        }

        connectBtn.setOnClickListener { connectWithInput() }
        scanBtn.setOnClickListener { scanLan() }
        changeBtn.setOnClickListener { showSetup() }

        requestNotificationPermission()

        if (prefs.url.isEmpty()) {
            showSetup()
        } else {
            addressInput.setText(prefs.url)
            openUrl(prefs.url)
        }
    }

    override fun onNewIntent(intent: Intent?) {
        super.onNewIntent(intent)
        if (intent?.getBooleanExtra("from_call", false) == true) {
            webView.reload()
        }
    }

    @Deprecated("兼容旧版返回键行为")
    override fun onBackPressed() {
        if (webView.visibility == View.VISIBLE && webView.canGoBack()) {
            webView.goBack()
        } else {
            @Suppress("DEPRECATION")
            super.onBackPressed()
        }
    }

    private fun showSetup() {
        setupScroll.visibility = View.VISIBLE
        webView.visibility = View.GONE
        changeBtn.visibility = View.GONE
    }

    private fun showWeb() {
        setupScroll.visibility = View.GONE
        webView.visibility = View.VISIBLE
        changeBtn.visibility = View.VISIBLE
    }

    private fun connectWithInput() {
        val parsed = parseAddress(addressInput.text.toString())
        if (parsed == null) {
            statusText.text = "地址不对。需要形如 http://192.168.1.5:3004/?t=abc123"
            return
        }
        val base = parsed.first
        val token = parsed.second
        val full = parsed.third
        prefs.url = full
        prefs.baseUrl = base
        prefs.token = token
        statusText.text = ""
        openUrl(full)
    }

    private fun parseAddress(raw: String): Triple<String, String, String>? {
        var text = raw.trim()
        if (text.isEmpty()) return null
        if (!text.startsWith("http://") && !text.startsWith("https://")) {
            text = "http://$text"
        }
        val uri = Uri.parse(text)
        val host = uri.host ?: return null
        val port = if (uri.port > 0) uri.port else 3004
        val token = uri.getQueryParameter("t")
        if (token.isNullOrEmpty()) return null
        val base = "http://$host:$port"
        return Triple(base, token, "$base/?t=$token")
    }

    private fun openUrl(url: String) {
        showWeb()
        webView.loadUrl(url)
        PollService.start(this)
    }

    private fun syncDeviceId(view: WebView?) {
        if (view == null) return
        val id = prefs.deviceId
        view.evaluateJavascript("localStorage.getItem('pkb-device-id')") { value ->
            val pageId = value?.trim('"')
            if (pageId != id) {
                view.evaluateJavascript("localStorage.setItem('pkb-device-id', '$id');", null)
                view.reload()
            }
        }
    }

    private fun requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            val granted = ContextCompat.checkSelfPermission(
                this, Manifest.permission.POST_NOTIFICATIONS
            ) == PackageManager.PERMISSION_GRANTED
            if (!granted) {
                ActivityCompat.requestPermissions(
                    this, arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1001
                )
            }
        }
    }

    private fun localPrefix(): String? {
        try {
            val interfaces = NetworkInterface.getNetworkInterfaces()
            for (iface in interfaces) {
                if (!iface.isUp || iface.isLoopback) continue
                for (address in iface.inetAddresses) {
                    if (address is Inet4Address && !address.isLoopbackAddress) {
                        val ip = address.hostAddress ?: continue
                        if (ip.startsWith("192.168.") || ip.startsWith("10.") || ip.startsWith("172.")) {
                            val parts = ip.split(".")
                            if (parts.size == 4) return "${parts[0]}.${parts[1]}.${parts[2]}"
                        }
                    }
                }
            }
        } catch (_: Exception) {
        }
        return null
    }

    private fun scanLan() {
        val prefix = localPrefix()
        if (prefix == null) {
            statusText.text = "没有连上 Wi-Fi。请先让手机和电脑连同一个 Wi-Fi。"
            return
        }
        statusText.text = "正在扫描 $prefix.x 网段，大约 10 秒…"
        scanBtn.isEnabled = false
        foundList.text = ""
        val found = java.util.Collections.synchronizedList(mutableListOf<String>())
        val remaining = AtomicInteger(254)
        for (i in 1..254) {
            val host = "$prefix.$i"
            scanPool.execute {
                try {
                    Socket().use { socket ->
                        socket.connect(InetSocketAddress(host, 3004), 500)
                        found.add(host)
                    }
                } catch (_: Exception) {
                } finally {
                    if (remaining.decrementAndGet() == 0) {
                        val snapshot = synchronized(found) { found.toList() }
                        runOnUiThread { onScanDone(snapshot) }
                    }
                }
            }
        }
    }

    private fun onScanDone(hosts: List<String>) {
        scanBtn.isEnabled = true
        if (hosts.isEmpty()) {
            statusText.text = "没找到电脑。确认电脑上的 PKB 正在运行，并且手机和电脑在同一个 Wi-Fi。"
            return
        }
        val token = prefs.token
        foundList.text = hosts.joinToString("\n")
        if (token.isNotEmpty()) {
            val target = "http://${hosts.first()}:3004/?t=$token"
            addressInput.setText(target)
            statusText.text = "找到 ${hosts.size} 台电脑，已自动填好地址，点「连接」即可。"
        } else {
            statusText.text = "找到 ${hosts.size} 台电脑。第一次使用需要把电脑上显示的完整地址粘贴进来（含令牌）。"
        }
    }
}
