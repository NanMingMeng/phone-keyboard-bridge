package com.nanming.pkb

import android.Manifest
import android.annotation.SuppressLint
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.view.View
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.EditText
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
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
    private lateinit var qrBtn: Button
    private lateinit var resumeBtn: Button
    private lateinit var scanBtn: Button
    private lateinit var changeBtn: Button
    private lateinit var statusText: TextView
    private lateinit var foundList: TextView
    private lateinit var helpToggle: Button
    private lateinit var helpBox: View
    private lateinit var manualToggle: Button
    private lateinit var manualBox: View

    private val scanPool = Executors.newFixedThreadPool(40)
    private val connectPool = Executors.newSingleThreadExecutor()

    private val qrScanLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == RESULT_OK) {
            val text = result.data?.getStringExtra(QrScanActivity.EXTRA_TEXT)?.trim().orEmpty()
            handleScanned(text)
        }
    }

    private val cameraPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) {
            qrScanLauncher.launch(Intent(this, QrScanActivity::class.java))
        } else {
            statusText.text = getString(R.string.qr_need_camera)
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        prefs = Prefs(this)

        webView = findViewById(R.id.webView)
        setupScroll = findViewById(R.id.setupScroll)
        addressInput = findViewById(R.id.addressInput)
        connectBtn = findViewById(R.id.connectBtn)
        qrBtn = findViewById(R.id.qrBtn)
        resumeBtn = findViewById(R.id.resumeBtn)
        scanBtn = findViewById(R.id.scanBtn)
        changeBtn = findViewById(R.id.changeBtn)
        statusText = findViewById(R.id.setupStatus)
        foundList = findViewById(R.id.foundList)
        helpToggle = findViewById(R.id.helpToggle)
        helpBox = findViewById(R.id.helpBox)
        manualToggle = findViewById(R.id.manualToggle)
        manualBox = findViewById(R.id.manualBox)

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
                if (url != null && !url.startsWith("about:")) {
                    prefs.lastOk = true
                    statusText.text = ""
                }
                syncDeviceId(view)
            }

            override fun onReceivedError(
                view: WebView?,
                request: WebResourceRequest?,
                error: WebResourceError?
            ) {
                super.onReceivedError(view, request, error)
                if (request?.isForMainFrame == true) {
                    val detail = error?.description?.toString().orEmpty()
                    failBackToSetup(
                        if (detail.isEmpty()) "打不开这个地址" else "打不开这个地址（$detail）"
                    )
                }
            }

            override fun onReceivedHttpError(
                view: WebView?,
                request: WebResourceRequest?,
                errorResponse: WebResourceResponse?
            ) {
                super.onReceivedHttpError(view, request, errorResponse)
                if (request?.isForMainFrame == true) {
                    failBackToSetup("电脑返回 HTTP ${errorResponse?.statusCode}，地址或令牌可能已失效")
                }
            }
        }

        connectBtn.setOnClickListener { connectWithInput() }
        qrBtn.setOnClickListener { startQrScan() }
        resumeBtn.setOnClickListener {
            val saved = prefs.url
            if (saved.isNotEmpty()) {
                openUrl(saved)
            } else {
                statusText.text = "还没有保存过地址，先扫码吧。"
            }
        }
        scanBtn.setOnClickListener { scanLan() }
        changeBtn.setOnClickListener { showSetup() }
        helpToggle.setOnClickListener {
            if (helpBox.visibility == View.VISIBLE) {
                helpBox.visibility = View.GONE
                helpToggle.text = getString(R.string.setup_help_toggle)
            } else {
                helpBox.visibility = View.VISIBLE
                helpToggle.text = getString(R.string.setup_help_hide)
            }
        }

        manualToggle.setOnClickListener {
            if (manualBox.visibility == View.VISIBLE) {
                manualBox.visibility = View.GONE
                manualToggle.text = getString(R.string.setup_manual_toggle)
            } else {
                manualBox.visibility = View.VISIBLE
                manualToggle.text = getString(R.string.setup_manual_hide)
            }
        }

        resumeBtn.visibility = if (prefs.url.isEmpty()) View.GONE else View.VISIBLE

        // 第一次用（还没有地址）就把连接条件摊开，先让人看一遍
        if (prefs.url.isEmpty()) {
            helpBox.visibility = View.VISIBLE
            helpToggle.text = getString(R.string.setup_help_hide)
        }

        requestNotificationPermission()

        if (prefs.url.isEmpty()) {
            showSetup()
        } else {
            addressInput.setText(prefs.url)
            if (prefs.lastOk) {
                openUrl(prefs.url)
            } else {
                showSetup()
                statusText.text = "上次没连上 ${prefs.baseUrl}。换了网络或热点后 IP 会变，请重新扫电脑上的二维码，或点「连接」重试。"
            }
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
        // 打字页按返回：页内有历史就回退，否则直接退到桌面。
        // 连接信息留在本地，下次打开自动回到打字页，不用重新扫码。
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

    /** 加载失败统一兜底：回到连接页并给一句人话，绝不把人丢在白屏里。 */
    private fun failBackToSetup(reason: String) {
        prefs.lastOk = false
        showSetup()
        addressInput.setText(prefs.url)
        manualBox.visibility = View.VISIBLE
        manualToggle.text = getString(R.string.setup_manual_hide)
        resumeBtn.visibility = if (prefs.url.isEmpty()) View.GONE else View.VISIBLE
        statusText.text = "$reason。已回到连接页：确认电脑上的 PKB 正在运行、手机和电脑在同一网络（同一 Wi‑Fi，或电脑连你手机的热点），再重新扫码或点「连接」。"
    }

    private fun startQrScan() {
        val granted = ContextCompat.checkSelfPermission(
            this, Manifest.permission.CAMERA
        ) == PackageManager.PERMISSION_GRANTED
        if (granted) {
            qrScanLauncher.launch(Intent(this, QrScanActivity::class.java))
        } else {
            cameraPermissionLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    private fun handleScanned(raw: String) {
        if (raw.isEmpty()) return
        val parsed = parseAddress(raw)
        if (parsed == null) {
            addressInput.setText(raw)
            statusText.text = getString(R.string.qr_invalid)
            return
        }
        addressInput.setText(parsed.third)
        statusText.text = ""
        Toast.makeText(this, "已扫码：${parsed.first}", Toast.LENGTH_SHORT).show()
        connectTo(parsed.first, parsed.second, parsed.third)
    }

    private fun connectWithInput() {
        val parsed = parseAddress(addressInput.text.toString())
        if (parsed == null) {
            statusText.text = "地址不对。需要形如 http://192.168.1.5:3004/?t=abc123"
            return
        }
        connectTo(parsed.first, parsed.second, parsed.third)
    }

    private fun connectTo(base: String, token: String, full: String) {
        prefs.url = full
        prefs.baseUrl = base
        prefs.token = token
        openUrl(full)
    }

    /** 先探一下端口能不能连上，再切到网页；连不上就留在连接页说明原因。 */
    private fun openUrl(url: String) {
        val uri = Uri.parse(url)
        val host = uri.host
        if (host.isNullOrEmpty()) {
            failBackToSetup("地址里没有主机名")
            return
        }
        val port = if (uri.port > 0) uri.port else 3004
        statusText.text = "正在连接 $host:$port …"
        connectPool.execute {
            val reachable = try {
                Socket().use { socket ->
                    socket.connect(InetSocketAddress(host, port), 1500)
                    true
                }
            } catch (_: Exception) {
                false
            }
            runOnUiThread {
                if (reachable) {
                    statusText.text = ""
                    showWeb()
                    webView.loadUrl(url)
                    PollService.start(this)
                } else {
                    prefs.lastOk = false
                    showSetup()
                    addressInput.setText(url)
                    manualBox.visibility = View.VISIBLE
                    manualToggle.text = getString(R.string.setup_manual_hide)
                    statusText.text =
                        "连不上 $host:$port。依次检查：① 电脑上的 PKB 正在运行；" +
                            "② 手机和电脑在同一网络（同一 Wi‑Fi，或电脑连你手机开的热点）；" +
                            "③ Windows 防火墙允许了 PKB；④ 换过网络或热点后 IP 会变，重新扫电脑上的二维码。"
                }
            }
        }
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
            statusText.text = "没找到电脑。确认电脑上的 PKB 正在运行，且手机和电脑在同一网络（同一 Wi‑Fi，或电脑连你手机的热点）。校园网、公司网常禁止设备互连，这种情况用手机热点最稳。"
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
